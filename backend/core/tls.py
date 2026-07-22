"""Certificat TLS local auto-signé pour servir OpenFlow en HTTPS.

Utilisé uniquement pour l'écoute locale (127.0.0.1 / localhost). Objectif :
permettre à Enable Banking (qui impose une redirection https) de renvoyer le
navigateur vers OpenFlow sans page d'erreur, pour un rapprochement bancaire
100% automatique. Le certificat est auto-signé : le navigateur affiche un
avertissement à accepter une seule fois.
"""
import ipaddress
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def ensure_dev_cert(cert_dir: Path) -> tuple[Path, Path]:
    """Génère (si absent) et renvoie (cert_path, key_path) pour localhost.

    Le certificat couvre localhost et 127.0.0.1 via SubjectAlternativeName, ce
    que les navigateurs modernes exigent (le Common Name seul ne suffit plus).
    """
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / "cert.pem"
    key_path = cert_dir / "key.pem"
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))

    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    san = x509.SubjectAlternativeName([
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
    ])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(san, critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path
