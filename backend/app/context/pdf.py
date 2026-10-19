"""Text-only PDF parsing with request-local parser resource limits."""

import logging
from io import BytesIO

from pypdf import PdfReader, apply_configuration

# Parser diagnostics can include malformed input. The API supplies sanitized errors instead.
logger = logging.getLogger("pypdf")
logger.addHandler(logging.NullHandler())
logger.propagate = False


def pdf_text(content: bytes, max_text: int) -> str:
    with apply_configuration(
        maximum_declared_stream_length=5_000_000,
        array_based_stream_maximum_output_length=5_000_000,
        zlib_maximum_output_length=5_000_000,
        lzw_maximum_output_length=5_000_000,
        run_length_maximum_output_length=5_000_000,
        brotli_maximum_output_length=5_000_000,
        stream_decoding_work_maximum_length=10_000_000,
        stream_parsing_work_maximum_count=100_000,
        page_tree_maximum_entries=101,
        xform_maximum_invocations_per_extraction=100,
        jbig2dec_binary=None,
    ):
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted or len(reader.pages) > 100:
            raise ValueError("Unsupported PDF")
        parts, text_size, stream_size = [], 0, 0
        for page in reader.pages:
            stream = page.get_contents()
            stream_size += len(stream.get_data()) if stream is not None else 0
            if stream_size > 20_000_000:
                raise ValueError("Oversized PDF content")
            text = page.extract_text() or ""
            text_size += len(text)
            if text_size > max_text:
                raise ValueError("Oversized PDF text")
            parts.append(text)
        return "\n\n".join(parts)
