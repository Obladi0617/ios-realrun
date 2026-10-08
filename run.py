"""
run.py
automatically run the route
"""

"""修正坐标误差，百度取点使用 BD-09 坐标系，iOS使用 WGS-09 坐标系，进行转换"""
import math
import os
import time
import random
import asyncio
from pathlib import Path

from geopy.distance import geodesic

from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider


STOP_FILE_ENV = "IOSREALRUN_STOP_FILE"


class RunStopped(Exception):
    """Raised when an external graceful-stop request is received."""


def stop_requested() -> bool:
    path = os.environ.get(STOP_FILE_ENV)
    if not path:
        return False
    return Path(path).exists()


DT = 0.2  # 定位推送间隔（秒）

# 配速波动档位，数值均来自公开研究：
# * Valencia 马拉松 2014-2023（146,108 名跑者）5 km 分段速度 CV：
#   女性 6.79 ± 5.14%，男性 7.40 ± 5.43%（Eur J Sport Sci, 2025）
# * 奥运长跑决赛：全程速度变异系数 3.6-11.4%，每 100 m 配速变化均值 1.6-2.7%
#   （Thiel et al., J Sports Sci, 2012）
# * 步态/步幅级变异远小于配速级变异（CV 约 1-4%）
# * 水平越低波动越大，后程降速越明显；水平越高越平稳
#   （Medicina 2026 综述、PLoS ONE 2026 波士顿马拉松 7.9 万人分析）
SPEED_PROFILES = {
    "steady":       {"cvPercent": 3.0,  "correlationTime": 25.0, "fatiguePercent": 1.5, "lapPercent": 1.5},
    "recreational": {"cvPercent": 6.0,  "correlationTime": 20.0, "fatiguePercent": 3.0, "lapPercent": 2.5},
    "variable":     {"cvPercent": 10.0, "correlationTime": 15.0, "fatiguePercent": 5.0, "lapPercent": 4.0},
}
DEFAULT_PROFILE = "recreational"


class PaceModel:
    """模拟真人跑步时的速度起伏。

    由三部分叠加，全部按目标速度的百分比计算，因此在任意配速下表现一致：

    1. 相关噪声（Ornstein-Uhlenbeck 过程）：速度不会独立乱跳，而是缓慢漂移，
       相关时间约 15-25 秒，稳态标准差等于设定的变异系数。
    2. 每圈偏移：每个圈速整体快一点或慢一点，对应文献中"分段配速"差异。
    3. 疲劳漂移：随时间缓慢降速，对应马拉松常见的后程减速。
    """

    def __init__(self, base_speed, dt=DT, cvPercent=6.0, correlationTime=20.0,
                 fatiguePercent=3.0, lapPercent=2.5, duration_seconds=None,
                 targetDistance=4000.0):
        self.base_speed = float(base_speed)
        self.dt = float(dt)
        self.cv = max(0.0, float(cvPercent)) / 100.0
        self.tau = max(1.0, float(correlationTime))
        self.fatigue = max(0.0, float(fatiguePercent)) / 100.0
        self.lap_sigma = max(0.0, float(lapPercent)) / 100.0
        self.fatigue_window = float(duration_seconds) if duration_seconds else 3600.0
        self.target_distance = max(1.0, float(targetDistance))
        self.min_speed = self.base_speed * 0.5

        # cvPercent 是期望的总变速系数，圈速偏移占掉一部分方差，其余交给相关噪声
        self.ou_sigma = math.sqrt(max(0.0, self.cv * self.cv - self.lap_sigma * self.lap_sigma))
        decay = math.exp(-self.dt / self.tau)
        self._decay = decay
        self._noise = math.sqrt(max(0.0, 1.0 - decay * decay)) * self.ou_sigma

        self.offset = 0.0
        self.lap_offset = 0.0
        self.current_speed = self.base_speed
        self.elapsed = 0.0
        self.distance = 0.0
        self.turn_factor = 1.0
        self.event_factor = 1.0
        self.event_remaining = 0.0
        self.next_event = random.uniform(45.0, 90.0)
        self.acceleration_tau = 1.5
        self.deceleration_tau = 2.5
        self._sum = 0.0
        self._sum_sq = 0.0
        self._count = 0

    def start_lap(self) -> None:
        self.lap_offset = random.gauss(0.0, self.lap_sigma) if self.lap_sigma else 0.0

    def speed(self) -> float:
        progress = min(1.0, self.distance / self.target_distance)
        drift = 1.0 - self.fatigue * progress ** 1.6
        factor = 1.0 + self.offset + self.lap_offset
        return max(self.min_speed, self.base_speed * factor * drift * self.turn_factor * self.event_factor)

    def step(self, turn_factor=1.0) -> float:
        self.offset = self.offset * self._decay + random.gauss(0.0, 1.0) * self._noise
        self.elapsed += self.dt
        self.turn_factor += (max(0.82, min(1.0, turn_factor)) - self.turn_factor) * min(1.0, self.dt / 0.8)

        self.next_event -= self.dt
        if self.event_remaining > 0.0:
            self.event_remaining -= self.dt
            if self.event_remaining <= 0.0:
                self.event_factor = 1.0
        elif self.next_event <= 0.0:
            event = random.random()
            if event < 0.18:
                # 业余跑者偶发的短暂恢复，保持移动但明显降速。
                self.event_factor = random.uniform(0.62, 0.78)
                self.event_remaining = random.uniform(2.0, 4.0)
            elif event < 0.70:
                self.event_factor = random.uniform(0.90, 0.96)
                self.event_remaining = random.uniform(1.5, 3.0)
            else:
                self.event_factor = random.uniform(1.03, 1.08)
                self.event_remaining = random.uniform(1.5, 3.0)
            self.next_event = random.uniform(45.0, 90.0)

        target_speed = self.speed()
        response_tau = self.acceleration_tau if target_speed >= self.current_speed else self.deceleration_tau
        self.current_speed += (target_speed - self.current_speed) * min(1.0, self.dt / response_tau)
        speed = max(self.min_speed, self.current_speed)
        self.distance += speed * self.dt
        self._sum += speed
        self._sum_sq += speed * speed
        self._count += 1
        return speed

    def reached_target(self) -> bool:
        return self.distance >= self.target_distance

    def mean_speed(self) -> float:
        return self._sum / self._count if self._count else self.base_speed

    def realized_cv(self) -> float:
        if self._count < 2:
            return 0.0
        mean = self.mean_speed()
        variance = max(0.0, self._sum_sq / self._count - mean * mean)
        return math.sqrt(variance) / mean * 100.0

    def describe(self) -> str:
        pace = 1000.0 / self.base_speed / 60.0
        return (
            f"基准 {self.base_speed:.2f} m/s（{int(pace)}:{int(pace % 1 * 60):02d}/km），"
            f"CV {self.cv * 100:.1f}%，相关时间 {self.tau:.0f}s，"
            f"目标 {self.target_distance / 1000:.1f}km，疲劳减速 {self.fatigue * 100:.1f}%"
        )


def build_pace_model(base_speed, dt=DT, duration_seconds=None, variation=None) -> PaceModel:
    options = dict(variation or {})
    profile = options.pop("profile", DEFAULT_PROFILE)
    target_distance = options.pop("targetDistance", 4000.0)
    settings = dict(SPEED_PROFILES.get(profile, SPEED_PROFILES[DEFAULT_PROFILE]))
    settings.update({key: value for key, value in options.items() if key in settings})
    return PaceModel(base_speed, dt=dt, duration_seconds=duration_seconds,
                     targetDistance=target_distance, **settings)


def bd09Towgs84(position):
    wgs_p = {}

    x_pi = 3.14159265358979324 * 3000.0 / 180.0
    pi = 3.141592653589793238462643383  # π
    a = 6378245.0  # 长半轴
    ee = 0.00669342162296594323  # 偏心率平方

    def transform_lat(x, y):
        ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
        ret += (20.0 * math.sin(6.0 * x * pi) + 20.0 * math.sin(2.0 * x * pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(y * pi) + 40.0 * math.sin(y / 3.0 * pi)) * 2.0 / 3.0
        ret += (160.0 * math.sin(y / 12.0 * pi) + 320 * math.sin(y * pi / 30.0)) * 2.0 / 3.0
        return ret

    def transform_lon(x, y):
        ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
        ret += (20.0 * math.sin(6.0 * x * pi) + 20.0 * math.sin(2.0 * x * pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(x * pi) + 40.0 * math.sin(x / 3.0 * pi)) * 2.0 / 3.0
        ret += (150.0 * math.sin(x / 12.0 * pi) + 300.0 * math.sin(x / 30.0 * pi)) * 2.0 / 3.0
        return ret

    x = position['lng'] - 0.0065
    y = position['lat'] - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * x_pi)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * x_pi)

    gcj_lng = z * math.cos(theta)
    gcj_lat = z * math.sin(theta)

    d_lat = transform_lat(gcj_lng - 105.0, gcj_lat - 35.0)
    d_lng = transform_lon(gcj_lng - 105.0, gcj_lat - 35.0)

    rad_lat = gcj_lat / 180.0 * pi
    magic = math.sin(rad_lat)
    magic = 1 - ee * magic * magic
    sqrt_magic = math.sqrt(magic)

    d_lng = (d_lng * 180.0) / (a / sqrt_magic * math.cos(rad_lat) * pi)
    d_lat = (d_lat * 180.0) / (a * (1 - ee) / (magic * sqrt_magic) * pi)

    wgs_p["lat"] = gcj_lat * 2 - gcj_lat - d_lat
    wgs_p["lng"] = gcj_lng * 2 - gcj_lng - d_lng
    return wgs_p

# get the ditance according to the latitude and longitude
def geodistance(p1, p2):
    return geodesic((p1["lat"],p1["lng"]),(p2["lat"],p2["lng"])).m

def smooth(start, end, i):
    i = (i-start)/(end-start)*math.pi
    return math.sin(i)**2

def randLoc(loc: list, d=0.000025, n=5):
    # deepcopy loc
    result = []
    for i in loc:
        result.append(i.copy())

    center = {"lat": 0, "lng": 0}
    for i in result:
        center["lat"] += i["lat"]
        center["lng"] += i["lng"]
    center["lat"] /= len(result)
    center["lng"] /= len(result)
    random.seed(time.time())
    for i in range(n):
        start = int(i*len(result)/n)
        end = int((i+1)*len(result)/n)
        offset = (2*random.random()-1) * d
        for j in range(start, end):
            distance = math.sqrt(
                (result[j]["lat"]-center["lat"])**2 + (result[j]["lng"]-center["lng"])**2
            )
            if 0 == distance:
                continue
            result[j]["lat"] +=  (result[j]["lat"]-center["lat"])/distance*offset*smooth(start, end, j)
            result[j]["lng"] +=  (result[j]["lng"]-center["lng"])/distance*offset*smooth(start, end, j)
    start = int(i*len(result)/n)
    end = len(result)
    offset = (2*random.random()-1) * d
    for j in range(start, end):
        distance = math.sqrt(
            (result[j]["lat"]-center["lat"])**2 + (result[j]["lng"]-center["lng"])**2
        )
        if 0 == distance:
            continue
        result[j]["lat"] +=  (result[j]["lat"]-center["lat"])/distance*offset*smooth(start, end, j)
        result[j]["lng"] +=  (result[j]["lng"]-center["lng"])/distance*offset*smooth(start, end, j)
    return result

def fixLockT(loc: list, v, dt):
    fixedLoc = []
    t = 0
    T = []
    T.append(geodistance(loc[1],loc[0])/v)
    a = loc[0].copy()
    b = loc[1].copy()
    j = 0
    while t < T[0]:
        xa = a["lat"] + j*(b["lat"]-a["lat"])/(max(1, int(T[0]/dt)))
        xb = a["lng"] + j*(b["lng"]-a["lng"])/(max(1, int(T[0]/dt)))
        fixedLoc.append({"lat": xa, "lng": xb})
        j += 1
        t += dt
    for i in range(1, len(loc)):
        T.append(geodistance(loc[(i+1)%len(loc)],loc[i])/v + T[-1])
        a = loc[i].copy()
        b = loc[(i+1)%len(loc)].copy()
        j = 0
        while t < T[i]:
            xa = a["lat"] + j*(b["lat"]-a["lat"])/(max(1, int((T[i]-T[i-1])/dt)))
            xb = a["lng"] + j*(b["lng"]-a["lng"])/(max(1, int((T[i]-T[i-1])/dt)))
            fixedLoc.append({"lat": xa, "lng": xb})
            j += 1
            t += dt
    return fixedLoc

async def run1(loc_sim, loc: list, model, dt=DT):
    """跑一圈，由配速模型控制瞬时速度。"""
    nominal = model.base_speed
    fixedLoc = fixLockT(loc, nominal, dt)
    nList = (5, 6, 7, 8, 9)
    n = nList[random.randint(0, len(nList)-1)]
    fixedLoc = randLoc(fixedLoc, n=n)  # a path will be divided into n parts for random route

    model.start_lap()
    last = len(fixedLoc) - 1
    index = 0.0
    while index < last:
        if stop_requested():
            raise RunStopped()
        position = min(int(index), last - 1)
        previous = fixedLoc[max(0, position - 1)]
        current = fixedLoc[position]
        following = fixedLoc[min(last, position + 1)]
        incoming = (current["lat"] - previous["lat"], current["lng"] - previous["lng"])
        outgoing = (following["lat"] - current["lat"], following["lng"] - current["lng"])
        incoming_size = math.hypot(*incoming)
        outgoing_size = math.hypot(*outgoing)
        turn_factor = 1.0
        if incoming_size and outgoing_size:
            cosine = max(-1.0, min(1.0, (incoming[0] * outgoing[0] + incoming[1] * outgoing[1]) /
                                    (incoming_size * outgoing_size)))
            turn_angle = math.acos(cosine)
            turn_factor = 1.0 - min(0.18, turn_angle / math.pi * 0.18)
        index += model.step(turn_factor=turn_factor) / nominal
        if model.reached_target():
            break
        position = int(index)
        if position >= last:
            break
        fraction = index - position
        start = fixedLoc[position]
        end = fixedLoc[position + 1]
        wgs = bd09Towgs84({
            "lat": start["lat"] + (end["lat"] - start["lat"]) * fraction,
            "lng": start["lng"] + (end["lng"] - start["lng"]) * fraction,
        })
        await loc_sim.set(wgs["lat"], wgs["lng"])
        await asyncio.sleep(dt)

async def run(address, port, loc: list, v, d=15, duration_seconds=None, variation=None):
    random.seed(time.time())
    model = build_pace_model(v, DT, duration_seconds, variation)
    print(f"速度波动：{model.describe()}", flush=True)
    rsd = RemoteServiceDiscoveryService((address, port))
    await asyncio.sleep(2)
    await rsd.connect()

    async with DvtProvider(rsd) as dvt:
        async with LocationSimulation(dvt) as loc_sim:
            try:
                async def _loop():
                    while True:
                        await run1(loc_sim, loc, model, dt=DT)
                        print(
                            f"跑完一圈了（{model.distance / 1000:.2f}/{model.target_distance / 1000:.1f} km，"
                            f"当前均值 {model.mean_speed():.2f} m/s，实测 CV {model.realized_cv():.1f}%）",
                            flush=True,
                        )
                        if model.reached_target():
                            print(f"已达到目标里程 {model.target_distance / 1000:.1f} km", flush=True)
                            break

                if duration_seconds:
                    await asyncio.wait_for(_loop(), timeout=duration_seconds)
                else:
                    await _loop()
            except RunStopped:
                print("收到停止请求，正在恢复真实定位...", flush=True)
            finally:
                try:
                    await loc_sim.clear()
                    print("已恢复真实定位", flush=True)
                except Exception as error:  # noqa: BLE001
                    print(f"清除模拟定位失败：{error}", flush=True)
