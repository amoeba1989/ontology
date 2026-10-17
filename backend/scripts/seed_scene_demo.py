"""python -m scripts.seed_scene_demo: additive, idempotent synthetic scene datasets."""
import json
from app.database import SessionLocal
from app.services.scene_demo import install_scene_demo


def main():
    with SessionLocal() as db:
        print(json.dumps(install_scene_demo(db), ensure_ascii=False))


if __name__ == '__main__':
    main()
