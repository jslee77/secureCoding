"""
플래그 자가채점.

각 취약점을 실제로 공략하면 자연스럽게 '증거값'(플래그)을 얻는다.
이 페이지에서 획득한 값을 입력해 맞았는지 확인한다.
정답은 SHA-256 해시로만 저장되어 있어 원본/공격법이 노출되지 않는다(채점만 가능).
"""
import hashlib
from flask import Blueprint, request, jsonify

bp = Blueprint("flags", __name__, url_prefix="/api/flags")


def _h(s):
    return hashlib.sha256(s.strip().encode()).hexdigest()


ANSWER_HASHES = {
    "2교시_인젝션": {
        "검색SQLi": "06a99c5b896cf45193af30523fccda27826f686c84e6304e31de79f191b7565f",
        "로그인우회": "95c149dc8418ae7f3a5dfc7c32e4c9a50c7bda86a4e65efb054252de2faa6ada",
        "SSTI": "eb500661626b935fdfd71b3c037f7cf11f99e88284ce4ad3b2298a447be942f3",
    },
    "3교시_파일경로": {
        "경로조작_DATA_KEY": "e6b3d4be7a3e8b834a30675f4a5e20f2252190d83ac936cd2d9a245d92e3a29e",
        "경로조작_서버노트": "61b906ab0ae711a4db0f4fd45016e5ac9d42641a681f3f9b1ada77cfb9d1d99e",
        "경로조작_JWT시크릿": "4e738ca5563c06cfd0018299933d58db1dd8bf97f6973dc99bf6cdc64b5550bd",
    },
    "4교시_인증": {
        "무솔트해시크랙": "8d059c3640b97180dd2ee453e20d34ab0cb0f2eccbe87d01915a8e578a202b11",
        "계정열거_숨은계정": "bbd6bfb2f752164deab9871907106ce81a9cc953f9868dabd0a99c14b4ca1031",
        "JWT위조_관리자키": "0171bec69b29346e482fbbe59bd0cca770c3a3a58c345c182337343960fad310",
    },
    "5교시_접근통제": {
        "IDOR_급여메모": "c42b1756bdfbb45b95c971e20e043d16973970a4e715cfcbcb1b26ff45d9cd43",
        "권한상승_마스터문서": "d5bb61e7d8ecfd1e428c1c5435a85dee5874a18c072e7020fc8a67e858ddbd7d",
    },
    "6교시_암호화": {
        "SSN복호화": "5a6eb782e1fe250dd2318fbbcf687e722646141a5335516eb0f58712a6301da0",
        "민감정보노출_관리자토큰": "1b6bfc2e3ec5dbb97898d35453c9352f8cb3b193c85b0f13234698de73d37ac0",
    },
    "7교시_예외로그": {
        "역직렬화RCE": "3a3212230bc5392f53e3c6be426c46591958a1e51c4177abf3811e8a4ed74810",
        "SSRF_내부메타": "98110f171afa40cc319b30c953ae8abfca0bda929948a745e7b410cd9a326e65",
    },
}


@bp.get("/list")
def list_flags():
    """모듈별 플래그 '개수/이름'만 공개(정답은 비공개)."""
    return jsonify({m: list(v.keys()) for m, v in ANSWER_HASHES.items()})


@bp.post("/check")
def check_flag():
    value = request.get_json(force=True).get("value", "")
    h = _h(value)
    for module, keys in ANSWER_HASHES.items():
        for key, ans in keys.items():
            if h == ans:
                return jsonify(ok=True, module=module, key=key,
                               message=f"정답! [{module}] {key}")
    return jsonify(ok=False, message="아직 아니에요. 다시 시도해보세요.")


@bp.post("/score")
def score():
    found = set(_h(v) for v in request.get_json(force=True).get("values", []))
    result, total_got, total_all = {}, 0, 0
    for module, keys in ANSWER_HASHES.items():
        got = sum(1 for ans in keys.values() if ans in found)
        result[module] = {"got": got, "total": len(keys)}
        total_got += got
        total_all += len(keys)
    return jsonify(modules=result, total={"got": total_got, "all": total_all})
