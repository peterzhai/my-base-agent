"""兼容 python -m backend.bootstrap；仅显式运行时进行初始化。"""

from backend.bootstrap.seeding import main

if __name__ == "__main__":
    main()
