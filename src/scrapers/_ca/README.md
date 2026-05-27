# BDDK CA bundle

`bddk_intermediates.pem` contains intermediate certificates that
`www.bddk.org.tr` fails to serve in its TLS handshake. Browsers
work around this via AIA chasing; Python's `ssl` module does not.

Combined with `certifi`'s root bundle by `src/scrapers/_http.py:bddk_verify()`
and used as `requests.verify=` for any BDDK call.

## Current contents
- `GlobalSign RSA OV SSL CA 2018` — intermediate for `*.bddk.org.tr`
  (leaf issued 2026-01-29, expires 2026-11-15). Downloaded from the
  AIA URL embedded in the leaf cert:
  http://secure.globalsign.com/cacert/gsrsaovsslca2018.crt

## When to refresh
- If BDDK rotates to a leaf issued by a different intermediate, add the
  new intermediate here (concatenated PEM is fine; `ssl` accepts
  multi-cert files). Probe with:

```python
import ssl, socket
ctx = ssl._create_unverified_context()
with socket.create_connection(("www.bddk.org.tr", 443)) as s:
    with ctx.wrap_socket(s, server_hostname="www.bddk.org.tr") as ts:
        der = ts.getpeercert(binary_form=True)
open("leaf.pem","w").write(ssl.DER_cert_to_PEM_cert(der))
# then: openssl x509 -in leaf.pem -noout -text | grep "CA Issuers"
```
