"""sam3 -- the SAM3 service (owner 1.8.1 + D2, 2026-09-29): the backend contract
(contract.py), the loader service with the "sam3" status row (loader.py) and the SAM3
model wrapper (model.py). Importing this package loads no model: torch arrives with
model.py, on the loader's thread (owner S3)."""
