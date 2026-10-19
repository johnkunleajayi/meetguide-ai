//! Per-source downmix and anti-aliased streaming resampling to 16 kHz mono PCM16.
use rubato::{
    Resampler, SincFixedIn, SincInterpolationParameters, SincInterpolationType, WindowFunction,
};
use std::collections::VecDeque;

pub struct PcmConverter {
    resampler: SincFixedIn<f32>,
    input: Vec<f32>,
    output: VecDeque<u8>,
    input_frames: usize,
    channels: u16,
}
impl PcmConverter {
    pub fn new(rate: u32, channels: u16) -> Result<Self, &'static str> {
        if !(8000..=384000).contains(&rate) || channels == 0 || channels > 32 {
            return Err("Unsupported transcription audio format.");
        }
        let input_frames = rate as usize / 50;
        let params = SincInterpolationParameters {
            sinc_len: 128,
            f_cutoff: 0.95,
            interpolation: SincInterpolationType::Linear,
            oversampling_factor: 128,
            window: WindowFunction::BlackmanHarris2,
        };
        let resampler = SincFixedIn::new(16000.0 / rate as f64, 1.0, params, input_frames, 1)
            .map_err(|_| "Unable to initialize streaming audio conversion.")?;
        Ok(Self {
            resampler,
            input: Vec::with_capacity(input_frames),
            output: VecDeque::with_capacity(1280),
            input_frames,
            channels,
        })
    }
    pub fn reset(&mut self) {
        self.input.clear();
        self.output.clear();
        self.resampler.reset();
    }
    pub fn feed(
        &mut self,
        bytes: &[u8],
        frames: u32,
        silent: bool,
        mut send: impl FnMut(Vec<u8>),
    ) -> Result<(), &'static str> {
        let stride = self.channels as usize * 4;
        if !silent && bytes.len() != frames as usize * stride {
            return Err("Invalid PCM frame length.");
        }
        for index in 0..frames as usize {
            let mono = if silent {
                0.0
            } else {
                bytes[index * stride..(index + 1) * stride]
                    .chunks_exact(4)
                    .map(|value| {
                        let sample = f32::from_le_bytes(value.try_into().expect("f32 sample"));
                        if sample.is_finite() {
                            sample.clamp(-1.0, 1.0)
                        } else {
                            0.0
                        }
                    })
                    .sum::<f32>()
                    / self.channels as f32
            };
            self.input.push(mono);
            if self.input.len() == self.input_frames {
                let output = self
                    .resampler
                    .process(&[&self.input], None)
                    .map_err(|_| "Streaming audio conversion failed.")?;
                self.input.clear();
                for sample in &output[0] {
                    self.output
                        .extend(((sample.clamp(-1.0, 1.0) * 32767.0).round() as i16).to_le_bytes());
                }
                while self.output.len() >= 640 {
                    send(self.output.drain(..640).collect());
                }
            }
        }
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rates_and_channels_become_bounded_20ms_mono_packets() {
        for rate in [16000, 44100, 48000, 96000] {
            let mut converter = PcmConverter::new(rate, 2).unwrap();
            let input: Vec<_> = (0..rate / 5)
                .flat_map(|_| [0.25f32.to_le_bytes(), 0.25f32.to_le_bytes()].concat())
                .collect();
            let mut packets = Vec::new();
            converter
                .feed(&input, rate / 5, false, |packet| packets.push(packet))
                .unwrap();
            assert!(packets.len() >= 8 && packets.len() <= 11);
            assert!(packets.iter().all(|packet| packet.len() == 640));
            converter.reset();
            let mut silent = Vec::new();
            converter
                .feed(&[], rate / 5, true, |packet| silent.extend(packet))
                .unwrap();
            assert!(silent.iter().all(|byte| *byte == 0));
        }
    }
}
