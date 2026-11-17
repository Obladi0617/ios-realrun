import argparse

import config
from init import route
from ios_session import run_async, run_ios
from session_control import RunStopped


async def main():
    parser = argparse.ArgumentParser(description="iOS RealRun virtual location runner")
    parser.add_argument("-m", "--minutes", type=int, default=0,
                        help="最长运行时长（分钟），默认达到约4公里后停止")
    args = parser.parse_args()
    if args.minutes < 0:
        parser.error("运行时长不能为负数")
    await run_ios(route.get_route(), config.config.v,
                  args.minutes * 60 if args.minutes else None,
                  getattr(config.config, "speedVariation", {}) or {})


if __name__ == "__main__":
    try:
        run_async(main())
    except (RunStopped, KeyboardInterrupt):
        print("操作已停止", flush=True)
