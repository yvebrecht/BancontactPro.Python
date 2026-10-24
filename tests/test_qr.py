from bancontactpro import BancontactEnvironment as E
from bancontactpro import QrCodeImageFormat as F
from bancontactpro import QrCodeImageSize as S
from bancontactpro import qr

# Worked examples published verbatim on https://docs.bancontactpro.com/guides/general/payloadurlupdate
PPID = "5c18cbd1296e9a26d3278518"


def test_fixed_amount_payload_matches_published_example():
    url = qr.build_fixed_amount_payment_url(E.PRODUCTION, PPID, 1000, "Receipt Payment", "sd89sd91?sd9")
    assert url == f"https://pay.bancontact.net/t/1/{PPID}?D=Receipt%20Payment&A=1000&R=sd89sd91%3Fsd9"


def test_qr_image_url_double_encodes_payload():
    payload = qr.build_fixed_amount_payment_url(E.PRODUCTION, PPID, 1000, "Receipt Payment", "sd89sd91?sd9")
    assert qr.build_qr_code_image_url(E.PRODUCTION, payload, F.PNG, S.XL) == (
        "https://qrcodegenerator.api.bancontact.net/qrcode?f=PNG&s=XL&c="
        "https%3A%2F%2Fpay.bancontact.net%2Ft%2F1%2F5c18cbd1296e9a26d3278518%3FD%3DReceipt%2520Payment"
        "%26A%3D1000%26R%3Dsd89sd91%253Fsd9"
    )


def test_static_qr_matches_published_example():
    payload = qr.build_static_qr_location_url(E.PRODUCTION, "5bb37284e35e2b29e363df22", "POS00001")
    assert payload == "https://pay.bancontact.net/l/1/5bb37284e35e2b29e363df22/POS00001"
    assert qr.build_qr_code_image_url(E.PRODUCTION, payload, F.PNG, S.XL).endswith(
        "c=https%3A%2F%2Fpay.bancontact.net%2Fl%2F1%2F5bb37284e35e2b29e363df22%2FPOS00001"
    )


def test_svg_omits_size_and_no_size_omits_s():
    assert "s=" not in qr.build_qr_code_image_url(E.PRODUCTION, "https://x", F.SVG, S.L)
    assert "s=" not in qr.build_qr_code_image_url(E.PRODUCTION, "https://x")


def test_preprod_hosts():
    assert qr.build_static_qr_location_url(E.PREPROD, "p", "POS1").startswith("https://pay.acc.bancontact.net/")
    assert qr.build_qr_code_image_url(E.PREPROD, "https://x").startswith("https://qrcodegenerator.api.preprod.bancontact.net/")
