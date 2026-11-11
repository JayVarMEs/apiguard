"""
Contract tests for APIGUARD S0 (Deliverable 2, Table "Component Interfaces").

Run without pytest:   python tests/test_normalizer.py
Run with pytest:      pytest tests/test_normalizer.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from apiguard.core.normalizer import (          # noqa: E402
    Normaliser, ParseFailure, SpecParseError,
    normalise_corpus, normalise_text,
)

OAS3 = """
openapi: 3.0.3
info: {title: Demo, version: "1.0"}
servers: [{url: "https://api.demo.test/v1"}]
security:
  - apiKeyAuth: []
components:
  securitySchemes:
    apiKeyAuth: {type: apiKey, in: header, name: X-API-Key}
  schemas:
    User:
      type: object
      required: [id]
      properties:
        id: {type: string, format: uuid}
        password: {type: string}
        manager: {$ref: '#/components/schemas/User'}   # circular on purpose
paths:
  /users/{userId}:
    parameters:
      - {name: userId, in: path, required: true, schema: {type: string}}
    get:
      operationId: getUser
      summary: Get one user
      responses:
        "200":
          description: ok
          content:
            application/json:
              schema: {$ref: '#/components/schemas/User'}
    delete:
      security: []          # explicit opt-out, NOT the same as inheriting
      responses: {"204": {description: gone}}
  /health:
    get:
      responses: {"200": {description: ok}}
"""

SWAGGER2 = """
swagger: "2.0"
info: {title: Demo, version: "1.0"}
host: api.demo.test
basePath: /v1
schemes: [https]
security:
  - apiKeyAuth: []
securityDefinitions:
  apiKeyAuth: {type: apiKey, in: header, name: X-API-Key}
definitions:
  User:
    type: object
    required: [id]
    properties:
      id: {type: string, format: uuid}
      password: {type: string}
paths:
  /users/{userId}:
    parameters:
      - {name: userId, in: path, required: true, type: string}
    get:
      operationId: getUser
      responses:
        "200": {description: ok, schema: {$ref: '#/definitions/User'}}
    post:
      parameters:
        - {name: body, in: body, required: true, schema: {$ref: '#/definitions/User'}}
      responses: {"201": {description: created}}
"""


def _by_key(spec):
    return {(e.method, e.path): e for e in spec.endpoints}


def test_every_endpoint_exactly_once():
    spec = normalise_text(OAS3, "oas3.yaml")
    keys = [(e.method, e.path) for e in spec.endpoints]
    assert len(keys) == len(set(keys)) == 3, keys


def test_path_level_parameters_are_merged_into_the_operation():
    e = _by_key(normalise_text(OAS3, "oas3.yaml"))[("get", "/users/{userId}")]
    names = {(p.name, p.location) for p in e.parameters}
    assert ("userId", "path") in names
    assert e.path_parameters == ["userId"]


def test_inherited_vs_overridden_security_are_distinguishable():
    ep = _by_key(normalise_text(OAS3, "oas3.yaml"))
    get_user = ep[("get", "/users/{userId}")]
    del_user = ep[("delete", "/users/{userId}")]
    assert get_user.security_source == "inherited"
    assert [s.scheme_name for s in get_user.security] == ["apiKeyAuth"]
    assert del_user.security_source == "override_none"   # security: []
    assert del_user.security == []


def test_circular_ref_is_cut_and_terminates():
    e = _by_key(normalise_text(OAS3, "oas3.yaml"))[("get", "/users/{userId}")]
    props = {p.path for p in e.responses[0].properties}
    assert "password" in props
    assert any(p.truncated for p in e.responses[0].properties)


def test_both_spec_versions_flatten_to_the_same_internal_form():
    a = _by_key(normalise_text(OAS3, "a.yaml"))[("get", "/users/{userId}")]
    b = _by_key(normalise_text(SWAGGER2, "b.yaml"))[("get", "/users/{userId}")]
    assert a.source_version != b.source_version
    for e in (a, b):
        assert e.operation_id == "getUser"
        assert e.security_source == "inherited"
        assert e.security[0].scheme_type == "apiKey"
        assert e.servers == ["https://api.demo.test/v1"]
        assert {p.path for p in e.responses[0].properties} >= {"id", "password"}


def test_swagger2_body_parameter_becomes_request_body():
    e = _by_key(normalise_text(SWAGGER2, "b.yaml"))[("post", "/users/{userId}")]
    assert e.request_body is not None and e.request_body.required
    assert {p.path for p in e.request_body.properties} >= {"id", "password"}
    # the body parameter must not leak into the plain parameter list
    assert all(p.location not in ("body", "formData") for p in e.parameters)


def test_unparsable_spec_is_logged_never_dropped(tmp_path=None):
    import tempfile, os
    d = tempfile.mkdtemp()
    bad = os.path.join(d, "broken.yaml")
    open(bad, "w").write("openapi: 3.0.0\npaths: [ this is not valid: :\n")
    good = os.path.join(d, "ok.yaml")
    open(good, "w").write(OAS3)
    results = list(normalise_corpus([bad, good]))
    failures = [f for _, f in results if f is not None]
    specs = [s for s, _ in results if s is not None]
    assert len(failures) == 1 and isinstance(failures[0], ParseFailure)
    assert len(specs) == 1


def test_determinism():
    a = [e.to_json() for e in normalise_text(OAS3, "x.yaml").endpoints]
    b = [e.to_json() for e in normalise_text(OAS3, "x.yaml").endpoints]
    assert a == b


def test_rejects_non_spec_document():
    try:
        normalise_text("hello: world", "no.yaml")
    except SpecParseError:
        return
    raise AssertionError("expected SpecParseError")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL  {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
