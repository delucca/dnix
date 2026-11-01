"""macOS Chromium cookie decryption, for use-slack.

macOS Chromium/Electron cookie values are encrypted as: Keychain "<App> Safe
Storage" password -> PBKDF2-HMAC-SHA1(salt="saltysalt", 1003 iters) -> 16-byte
AES-128-CBC key (fixed 0x20*16 IV) -> ciphertext with a ``v10``/``v11`` prefix
and, on Chrome 130+, a 32-byte SHA256(host_key) host-binding prefix on the
plaintext, stripped only when it matches.

The AES step uses the ``cryptography`` package when importable (use-slack runs
under uv with it pinned), else the ``openssl`` CLI. Both yield identical
plaintext.
"""
from __future__ import annotations

import hashlib
import subprocess

_IV = b" " * 16          # Chromium uses 16 bytes of 0x20 as the CBC IV
_SALT = b"saltysalt"
_ITERATIONS = 1003
_KEYLEN = 16


class CookieDecryptError(Exception):
    """A cookie value could not be decrypted to valid plaintext."""


def keychain_password(service: str, account: str | None = None) -> bytes:
    """Read a "<App> Safe Storage" password from the macOS login keychain."""
    cmd = ["security", "find-generic-password", "-w", "-s", service]
    if account:
        cmd += ["-a", account]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise CookieDecryptError(
            f"Keychain lookup failed for {service!r}: {result.stderr.strip()}"
        )
    return result.stdout.strip().encode("utf-8")


def derive_key(password: bytes) -> bytes:
    """PBKDF2-HMAC-SHA1(password, 'saltysalt', 1003) -> the 16-byte AES key."""
    return hashlib.pbkdf2_hmac("sha1", password, _SALT, _ITERATIONS, dklen=_KEYLEN)


def _aes_cbc_decrypt(key: bytes, ciphertext: bytes) -> bytes:
    """AES-128-CBC decrypt with Chromium's fixed IV; no unpadding here.

    Prefers the ``cryptography`` package (fast path in use-slack's uv env); falls
    back to the ``openssl`` CLI for a stdlib-only Python.
    """
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:
        return _aes_cbc_decrypt_openssl(key, ciphertext)
    decryptor = Cipher(algorithms.AES(key), modes.CBC(_IV)).decryptor()
    return decryptor.update(ciphertext) + decryptor.finalize()


def _aes_cbc_decrypt_openssl(key: bytes, ciphertext: bytes) -> bytes:
    # SECURITY NOTE: -K puts the AES key on the argv, briefly readable by any
    # local process via `ps` for the life of each openssl call. Accepted as a
    # single-user-machine tradeoff for staying dependency-free; the caller uses
    # the in-process `cryptography` path (no argv exposure) wherever it is
    # importable, so this fallback only runs under a stdlib-only interpreter.
    result = subprocess.run(
        ["openssl", "enc", "-d", "-aes-128-cbc",
         "-K", key.hex(), "-iv", _IV.hex(), "-nosalt", "-nopad"],
        input=ciphertext, capture_output=True,
    )
    if result.returncode != 0:
        raise CookieDecryptError(
            "openssl AES decrypt failed: "
            + result.stderr.decode(errors="replace").strip()
        )
    return result.stdout


def decrypt_cookie(encrypted_value: bytes, key: bytes, host_key: str = "") -> str:
    """Decrypt a Chromium ``v10``/``v11`` cookie value to text (canonical logic).

    * requires a v10/v11 prefix -- an unknown prefix raises rather than returning
      the raw ciphertext as garbage;
    * validates the trailing PKCS7 pad byte is 1..16;
    * strips the leading 32-byte SHA256(``host_key``) host-binding prefix ONLY
      when it matches (Chrome 130+), so older/unbound cookies are left intact.

    Pass the cookie row's ``host_key`` to enable the conditional strip; omit it
    (default "") to skip the strip entirely.
    """
    if not encrypted_value:
        raise CookieDecryptError("empty encrypted value")
    prefix = encrypted_value[:3]
    if prefix not in (b"v10", b"v11"):
        raise CookieDecryptError(f"unsupported cookie version: {prefix!r}")
    plain = _aes_cbc_decrypt(key, encrypted_value[3:])
    if not plain:
        raise CookieDecryptError("decryption produced no output")
    pad = plain[-1]
    if pad < 1 or pad > 16:
        raise CookieDecryptError(f"invalid PKCS7 padding: {pad}")
    plain = plain[:-pad]
    if host_key:
        expected = hashlib.sha256(host_key.encode("utf-8")).digest()
        if len(plain) >= 32 and plain[:32] == expected:
            plain = plain[32:]
    return plain.decode("utf-8", errors="replace")
