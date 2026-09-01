from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[2]
BACKEND_DOCKERFILES = (
    PROJECT_ROOT / "deploy" / "Dockerfile.backend",
    PROJECT_ROOT / "deploy" / "Dockerfile.dev",
)
TIKTOKEN_CACHE_ENV = "TIKTOKEN_CACHE_DIR=/app/var/cache/tiktoken"
CL100K_CACHE_KEY = "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
CL100K_SHA256 = (
    "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
)


def test_backend_images_seed_verified_tiktoken_cache_with_explicit_ownership():
    for dockerfile in BACKEND_DOCKERFILES:
        source = dockerfile.read_text(encoding="utf-8")
        assert TIKTOKEN_CACHE_ENV in source, dockerfile
        assert CL100K_CACHE_KEY in source, dockerfile
        assert CL100K_SHA256 in source, dockerfile
        assert "sha256sum -c" in source, dockerfile
        assert "chown" in source, dockerfile


def test_non_backend_images_do_not_receive_server_tokenizer_cache():
    for relative_path in ("deploy/Dockerfile.web", "Dockerfile.sandbox"):
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert TIKTOKEN_CACHE_ENV not in source, relative_path
