"""별도 제한 프로세스에서 파일 파싱. python file_validation.py PATH EXT"""
import sys
import warnings


def validate(path, extension):
    if extension == ".txt":
        with open(path, encoding="utf-8") as stream:
            text = stream.read()
        if any(ord(c) < 32 and c not in "\t\r\n" for c in text):
            raise ValueError("Not plain text")
    elif extension == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path, strict=True)
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 100:
            raise ValueError("Encrypted or oversized PDF")
        # 형식 검증이며 악성코드 검사/CDR를 대체하지 않는다.
    else:
        from PIL import Image
        formats = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".gif": "GIF"}
        Image.MAX_IMAGE_PIXELS = 20_000_000
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as im:
            if im.format != formats[extension]:
                raise ValueError("Extension mismatch")
            if im.width * im.height * getattr(im, "n_frames", 1) > 20_000_000:
                raise ValueError("Too many pixels")
            im.verify()
        with Image.open(path) as im:
            for frame in range(getattr(im, "n_frames", 1)):
                im.seek(frame)
                im.load()


if __name__ == "__main__":
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    # Linux 컨테이너에는 주소 공간 상한도 적용한다(macOS는 지원 차이 있음).
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    try:
        validate(sys.argv[1], sys.argv[2])
    except Exception:
        sys.exit(1)
