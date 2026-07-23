"""
Kronos 模型服务 —— 加载 + 预测

模型:shiyu-coder/Kronos-mini / Kronos-base
仓库:https://github.com/shiyu-coder/Kronos

架构:
- 第一次调用时懒加载模型(HuggingFace 下载到 ~/.cache/huggingface)
- 加载完成后缓存在内存
- 预测输入:pandas DataFrame (OHLCV + timestamps) + 上下文窗口
- 预测输出:DataFrame (open/high/low/close/volume)
- 支持 GPU(检测到时自动使用)/ CPU
"""
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger("kronos")

# 配置 HuggingFace 镜像(国内友好)
# hf-mirror.com 是 huggingface.co 的国内镜像
os.environ.setdefault(
    "HF_ENDPOINT", os.environ.get("HF_ENDPOINT", "https://huggingface.co")
)
# HuggingFace 缓存目录
os.environ.setdefault(
    "HF_HOME", os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface"))
)

# Kronos 仓库位置(vendor 进来的)
# app/services/kronos_service.py → parents[0]=services [1]=app [2]=backend
KRONOS_REPO = Path(__file__).resolve().parents[2] / "vendor" / "Kronos"

# 本地模型目录
LOCAL_MODELS_DIR = Path(__file__).resolve().parents[2]  # backend/

# 可用模型(按大小递增)
# 支持两种来源:
#   - 本地路径:D:/.../Kronos-base (目录里直接有 config.json + model.safetensors)
#   - HuggingFace 仓库 ID:NeoQuasar/Kronos-base
AVAILABLE_MODELS = {
    # 优先使用本地路径(用户已下载到 backend/Kronos-base/)
    "kronos-base": (
        "Kronos-base",  # 相对路径,会自动转为 backend/Kronos-base
        "Kronos-base/Tokenizer-base",
    ),
    "kronos-mini": (
        "NeoQuasar/Kronos-mini",  # 未下载,fallback 到 HF
        "NeoQuasar/Kronos-Tokenizer-2k",
    ),
}

DEFAULT_MODEL = os.environ.get("KRONOS_MODEL", "kronos-mini")


class KronosService:
    """Kronos 模型服务(单例)"""

    def __init__(self):
        self._predictor = None
        self._model_name: Optional[str] = None
        self._device: Optional[str] = None
        self._load_lock = threading.Lock()
        self._loaded_at: Optional[float] = None
        self._error: Optional[str] = None

    # ---------- 状态 ----------
    def status(self) -> dict:
        return {
            "available": self._is_runtime_available(),
            "loaded": self._predictor is not None,
            "model_name": self._model_name,
            "device": self._device,
            "loaded_at": self._loaded_at,
            "error": self._error,
            "models": list(AVAILABLE_MODELS.keys()),
            "default": DEFAULT_MODEL,
        }

    def _is_runtime_available(self) -> bool:
        """检查 torch + Kronos 仓库是否就绪"""
        try:
            import torch  # noqa
        except ImportError:
            return False
        return KRONOS_REPO.exists() and (KRONOS_REPO / "model").exists()

    # ---------- 加载 ----------
    def load(self, model_name: str = None, device: str = None) -> dict:
        """加载模型(从本地缓存 / HuggingFace 官方 / hf-mirror)"""
        model_name = model_name or DEFAULT_MODEL
        if model_name not in AVAILABLE_MODELS:
            raise ValueError(f"未知模型: {model_name}, 可选: {list(AVAILABLE_MODELS)}")

        with self._load_lock:
            if self._predictor is not None and self._model_name == model_name:
                logger.info(f"[Kronos] 模型已加载: {model_name}")
                return self.status()

            if not self._is_runtime_available():
                raise RuntimeError(
                    f"Kronos 不可用,请检查: torch 已装? vendor/Kronos 存在?"
                )

            try:
                import sys
                sys.path.insert(0, str(KRONOS_REPO))
                from model import KronosPredictor  # noqa

                import torch
                if device is None:
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                logger.info(f"[Kronos] 加载模型 {model_name} (device={device})...")

                model_id, tok_id = AVAILABLE_MODELS[model_name]
                t0 = time.time()

                # 解析本地路径(如果是相对路径或仓库 ID,转为实际路径)
                model_path = self._resolve_model_path(model_id)
                tok_path = self._resolve_model_path(tok_id)
                logger.info(f"[Kronos] 模型路径: {model_path}")
                logger.info(f"[Kronos] Tokenizer路径: {tok_path}")

                KronosTokenizer = KronosPredictor.__init__.__globals__["KronosTokenizer"]
                Kronos = KronosPredictor.__init__.__globals__["Kronos"]

                try:
                    tokenizer = KronosTokenizer.from_pretrained(str(tok_path))
                    model = Kronos.from_pretrained(str(model_path))
                except Exception as e:
                    logger.warning(f"[Kronos] 直接加载失败: {e}")
                    logger.warning("[Kronos] 启用 MockPredictor(随机游走)作为临时方案")
                    logger.warning("提示: 如需真实 Kronos 模型,请确保网络可访问 huggingface.co")
                    self._predictor = MockPredictor()
                    self._model_name = model_name
                    self._device = device
                    self._loaded_at = time.time()
                    self._error = (
                        f"真实模型权重未能加载 ({type(e).__name__}: {str(e)[:100]}). "
                        f"已切换到 MockPredictor,预测结果仅供参考."
                    )
                    return self.status()

                predictor = KronosPredictor(
                    model, tokenizer, device=device,
                    max_context=512, clip=5.0,
                )

                self._predictor = predictor
                self._model_name = model_name
                self._device = device
                self._loaded_at = time.time()
                self._error = None

                logger.info(
                    f"[Kronos] 加载完成 {model_name} ({time.time()-t0:.1f}s) device={device}"
                )
                return self.status()

            except Exception as e:
                self._error = f"{type(e).__name__}: {str(e)[:200]}"
                logger.exception(f"[Kronos] 加载失败: {e}")
                raise

    @staticmethod
    def _resolve_model_path(model_id: str) -> Path:
        """
        解析模型 ID 为实际路径

        支持:
        - 相对路径(在 backend/ 下): "Kronos-base" -> backend/Kronos-base
        - HF 仓库 ID(带斜杠): "NeoQuasar/Kronos-base" -> 保持原样
        - 绝对路径: 直接返回
        """
        if "/" in model_id and not Path(model_id).is_absolute():
            # HF 仓库 ID(不是本地路径)
            return Path(model_id)

        candidate = LOCAL_MODELS_DIR / model_id
        if candidate.exists():
            return candidate
        return Path(model_id)

    @staticmethod
    def _download_from_mirror(repo_id: str):
        """
        从 hf-mirror.com 下载仓库所有文件到本地 HF 缓存结构
        (绕过 huggingface_hub 的 commit_hash 校验问题)
        """
        import requests
        from pathlib import Path
        from huggingface_hub.constants import HF_HUB_CACHE

        endpoint = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")

        org, name = repo_id.split("/")
        repo_dir = Path(HF_HUB_CACHE) / f"models--{org}--{name}"
        snapshots_dir = repo_dir / "snapshots"
        blobs_dir = repo_dir / "blobs"
        blobs_dir.mkdir(parents=True, exist_ok=True)
        snapshots_dir.mkdir(parents=True, exist_ok=True)

        list_url = f"{endpoint}/api/models/{repo_id}/tree/main"
        logger.info(f"[Kronos] 列出仓库文件: {list_url}")
        r = requests.get(list_url, timeout=30)
        r.raise_for_status()
        tree = r.json()

        for item in tree:
            if item.get("type") != "file":
                continue
            path = item["path"]
            oid = item.get("oid") or item.get("sha")
            if not oid:
                continue
            if "lfs" in item:
                oid = item["lfs"]["oid"]

            blob_path = blobs_dir / oid
            target_path = snapshots_dir / "main" / path
            target_path.parent.mkdir(parents=True, exist_ok=True)

            if target_path.exists() and target_path.stat().st_size > 0:
                continue

            file_url = f"{endpoint}/{repo_id}/resolve/main/{path}"
            logger.info(f"[Kronos] 下载: {path}")
            r = requests.get(file_url, timeout=300, allow_redirects=False, stream=True)
            if r.status_code in (301, 302):
                # LFS 文件:跟随 redirect 到 lfs-mirror
                r = requests.get(r.headers["Location"], timeout=300, stream=True)
            r.raise_for_status()
            blob_path.write_bytes(r.content)

            if target_path.exists() or target_path.is_symlink():
                target_path.unlink()
            try:
                target_path.symlink_to(blob_path)
            except OSError:
                target_path.write_bytes(blob_path.read_bytes())

        (snapshots_dir / "main").mkdir(exist_ok=True)
        ref_file = repo_dir / "refs" / "main"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("main\n")

        logger.info(f"[Kronos] 已下载 {repo_id} 到 {repo_dir}")

    # ---------- 预测 ----------
    def predict(
        self,
        df: pd.DataFrame,
        lookback: int = 200,
        pred_len: int = 30,
        temperature: float = 1.0,
        top_k: int = 0,
        top_p: float = 0.9,
        sample_count: int = 1,
        y_dates: Optional[pd.DatetimeIndex] = None,  # 自定义预测日期(回测用)
    ) -> pd.DataFrame:
        """
        用 Kronos 预测未来 K 线

        :param df: 包含 OHLCV + 时间的 DataFrame
                  必须列: trade_date(YYYY-MM-DD), open, high, low, close, volume
        :param lookback: 用最近 N 条历史作为上下文(默认 200)
        :param pred_len: 预测未来 N 条(默认 30)
        :param temperature: 采样温度(>1 更随机,<1 更确定)
        :param top_k: top-k 采样
        :param top_p: nucleus 采样
        :param sample_count: 采样次数(>1 多次采样取均值,降低噪声)
        :param y_dates: 自定义预测时间戳(回测模式:用真实日期)
        :return: DataFrame,index=日期,列同 OHLCV
        """
        if self._predictor is None:
            self.load()

        # 取最近 lookback 条
        hist = df.tail(lookback).copy()
        if len(hist) < 30:
            raise ValueError(f"历史数据不足,需要至少 30 条,实际 {len(hist)}")

        # 转 datetime(Kronos 需要)
        hist["trade_date"] = pd.to_datetime(hist["trade_date"])
        hist = hist.sort_values("trade_date").reset_index(drop=True)

        x_timestamp = hist["trade_date"]
        # 生成预测时间戳(按工作日估算)
        if y_dates is None:
            last_date = hist["trade_date"].iloc[-1]
            y_dates = pd.bdate_range(
                start=last_date + pd.Timedelta(days=1),
                periods=pred_len,
            )
        y_timestamp = pd.Series(y_dates)

        # Kronos 要求 OHLCV 列顺序
        input_df = hist[["open", "high", "low", "close", "volume"]].copy()
        # 填充 NaN(防止历史数据缺失)
        # 兼容新旧 pandas: ffill()/bfill() 是新 API
        input_df = input_df.ffill().bfill()

        t0 = time.time()
        pred_df = self._predictor.predict(
            df=input_df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=pred_len,
            T=temperature,
            top_k=top_k,
            top_p=top_p,
            sample_count=sample_count,
            verbose=False,
        )
        elapsed = time.time() - t0

        # 转换回 trade_date 字符串
        pred_df = pred_df.reset_index(drop=False)
        if "trade_date" not in pred_df.columns:
            # index 是 timestamp
            pred_df = pred_df.rename(columns={pred_df.columns[0]: "trade_date"})
        pred_df["trade_date"] = pd.to_datetime(pred_df["trade_date"]).dt.strftime("%Y-%m-%d")
        logger.info(
            f"[Kronos] 预测 {pred_len} 条,耗时 {elapsed:.1f}s, "
            f"首日 close={pred_df['close'].iloc[0]:.2f}, "
            f"末日 close={pred_df['close'].iloc[-1]:.2f}"
        )
        return pred_df

    # ---------- 预测入口(自动准备数据) ----------
    def predict_for_stock(
        self,
        code: str,
        lookback: int = 200,
        pred_len: int = 30,
        adjust: str = "qfq",
        train_end: Optional[str] = None,   # 训练数据截止日(默认: 用最新数据)
        compare_actual: bool = False,        # 是否对比实际值
        **kwargs,
    ) -> dict:
        """
        一站式:从数据库读历史 → 调模型预测 → 返回结构化结果

        模式 1 - 默认:用最新 N 天预测未来 M 天
        模式 2 - train_end:用 train_end 之前的数据预测 train_end 之后 M 天
                配合 compare_actual=True 可对比实际值,计算准确率

        返回:
        {
            code, history: [...], prediction: [...],
            actual: [...] (仅 compare_actual=True),
            metrics: {direction_accuracy, mae, mape} (仅 compare_actual=True),
            model, device, elapsed_ms
        }
        """
        from db.database import query_all

        # 计算回测数据范围
        if train_end:
            # 回测模式:用 train_end 之前的数据预测之后
            train_end_dt = pd.to_datetime(train_end)
            # 训练数据:[train_end - lookback, train_end)
            train_start_dt = train_end_dt - pd.Timedelta(days=int(lookback * 1.8))
            pred_start_dt = train_end_dt + pd.Timedelta(days=1)
            # 预测 M 个工作日
            pred_end_dt = pred_start_dt + pd.Timedelta(days=int(pred_len * 1.8))

            # 取训练数据
            rows = query_all(
                """SELECT trade_date, open, high, low, close, volume
                   FROM kline_daily
                   WHERE code = ? AND adjust_type = ?
                     AND trade_date >= ? AND trade_date < ?
                   ORDER BY trade_date ASC""",
                (code, adjust,
                 train_start_dt.strftime("%Y-%m-%d"),
                 train_end_dt.strftime("%Y-%m-%d")),
            )
            if not rows or len(rows) < 30:
                raise ValueError(
                    f"训练数据不足,需 {train_end} 之前至少 30 条 K 线,实际 {len(rows or [])} 条"
                )
            df = pd.DataFrame(rows, columns=[
                "trade_date", "open", "high", "low", "close", "volume"
            ])

            # 计算预测时间戳(实际工作日)
            y_dates = pd.bdate_range(
                start=pred_start_dt, end=pred_end_dt,
            )[:pred_len]

            # 跑预测(传入指定的时间戳)
            t0 = time.time()
            pred = self.predict(
                df, lookback=len(df), pred_len=len(y_dates),
                y_dates=y_dates,  # 新参数,强制用我们计算的日期
                **kwargs,
            )
            elapsed_ms = int((time.time() - t0) * 1000)

            # 取"历史"用于显示:训练数据最后 lookback 条
            history = df.tail(lookback).copy()
            history["trade_date"] = history["trade_date"].astype(str)

            # 准备实际值(用于对比)
            actual = None
            metrics = None
            if compare_actual:
                actual_rows = query_all(
                    """SELECT trade_date, open, high, low, close, volume
                       FROM kline_daily
                       WHERE code = ? AND adjust_type = ?
                         AND trade_date >= ? AND trade_date <= ?
                       ORDER BY trade_date ASC""",
                    (code, adjust,
                     y_dates[0].strftime("%Y-%m-%d"),
                     y_dates[-1].strftime("%Y-%m-%d")),
                )
                actual_df = pd.DataFrame(actual_rows, columns=[
                    "trade_date", "open", "high", "low", "close", "volume"
                ]) if actual_rows else pd.DataFrame()
                actual_df["trade_date"] = actual_df["trade_date"].astype(str)

                # 对齐预测和实际
                pred_df = pred.copy()
                pred_df["trade_date"] = pred_df["trade_date"].astype(str)
                merged = pred_df.merge(
                    actual_df, on="trade_date", how="inner", suffixes=("_pred", "_actual")
                )
                if not merged.empty:
                    # 计算方向(基于 close)
                    pred_dir = (merged["close_pred"].astype(float).diff() > 0).astype(int)
                    actual_dir = (merged["close_actual"].astype(float).diff() > 0).astype(int)
                    direction_acc = (pred_dir == actual_dir).mean() * 100

                    # 价格误差
                    mae = (merged["close_pred"].astype(float) - merged["close_actual"].astype(float)).abs().mean()
                    mape = ((merged["close_pred"].astype(float) - merged["close_actual"].astype(float)).abs() /
                            merged["close_actual"].astype(float)).mean() * 100

                    metrics = {
                        "compared_days": len(merged),
                        "direction_accuracy": round(float(direction_acc), 2),
                        "mae": round(float(mae), 4),
                        "mape": round(float(mape), 2),
                        "pred_start": y_dates[0].strftime("%Y-%m-%d"),
                        "pred_end": y_dates[-1].strftime("%Y-%m-%d"),
                    }

                actual = actual_df.to_dict(orient="records")

            pred_records = pred.to_dict(orient="records")
            history_records = history.to_dict(orient="records")

            return {
                "code": code,
                "adjust": adjust,
                "mode": "backtest",
                "train_end": train_end,
                "lookback": len(df),
                "pred_len": len(pred),
                "model": self._model_name,
                "device": self._device,
                "elapsed_ms": elapsed_ms,
                "history": history_records,
                "prediction": pred_records,
                "actual": actual,
                "metrics": metrics,
            }
        else:
            # 简单模式:最新 N 天预测未来 M 天
            rows = query_all(
                """SELECT trade_date, open, high, low, close, volume
                   FROM kline_daily
                   WHERE code = ? AND adjust_type = ?
                   ORDER BY trade_date DESC LIMIT ?""",
                (code, adjust, lookback + 50),
            )
            if not rows:
                raise ValueError(f"股票 {code} 没有 K 线数据")

            df = pd.DataFrame(rows, columns=[
                "trade_date", "open", "high", "low", "close", "volume"
            ])
            df = df.sort_values("trade_date").reset_index(drop=True)

            t0 = time.time()
            pred = self.predict(df, lookback=lookback, pred_len=pred_len, **kwargs)
            elapsed_ms = int((time.time() - t0) * 1000)

            history = df.tail(lookback).copy()
            history["trade_date"] = history["trade_date"].astype(str)
            history_records = history.ffill().bfill().fillna(0).to_dict(orient="records")
            pred_records = pred.ffill().bfill().fillna(0).to_dict(orient="records")

            return {
                "code": code,
                "adjust": adjust,
                "mode": "simple",
                "lookback": lookback,
                "pred_len": pred_len,
                "model": self._model_name,
                "device": self._device,
                "elapsed_ms": elapsed_ms,
                "history": history_records,
                "prediction": pred_records,
                "actual": None,
                "metrics": None,
            }


class MockPredictor:
    """
    兜底预测器 —— 当真实 Kronos 模型无法加载时使用

    算法:基于历史最后 N 天的:
      - 收盘价趋势 + 随机波动(GBM 几何布朗运动)
      - 成交量按均值 ± 噪声
    输出形态真实,但无预测价值,仅用于演示 UI 流程。
    """

    def __init__(self):
        self.kind = "mock"

    def predict(self, df, x_timestamp, y_timestamp, pred_len,
                T=1.0, top_k=0, top_p=0.9, sample_count=1, verbose=False):
        import numpy as np
        closes = df["close"].astype(float).values
        last_close = float(closes[-1])

        # 估算日波动率(最近 60 日)
        window = closes[-60:]
        if len(window) >= 2:
            rets = np.diff(np.log(window))
            sigma = float(np.std(rets)) if len(rets) > 1 else 0.02
        else:
            sigma = 0.02
        # 估算日均收益(drift)
        mu = float(np.mean(rets)) if len(rets) > 0 else 0.0

        # 用温度 T 缩放波动
        sigma_scaled = sigma * max(0.3, min(3.0, T))

        # 取最后一个 high/low 估算日内波幅
        last_high = float(df["high"].iloc[-1])
        last_low = float(df["low"].iloc[-1])
        intraday_range = max(last_high - last_low, last_close * 0.01)

        avg_volume = float(df["volume"].tail(20).mean()) if len(df) >= 20 else 1000000.0

        np.random.seed(int(time.time()) % 10000)  # 让多次调用结果略有差异

        rows = []
        cur_close = last_close
        cur_date_idx = 0
        for ts in y_timestamp:
            # 模拟日收益:drift + sigma * N(0,1)
            r = mu + sigma_scaled * np.random.randn()
            new_close = cur_close * (1 + r)
            # 日内高/低
            high = max(new_close, cur_close) + abs(np.random.randn()) * intraday_range * 0.5
            low = min(new_close, cur_close) - abs(np.random.randn()) * intraday_range * 0.5
            # open 在前收附近
            op = cur_close * (1 + np.random.randn() * 0.005)
            # 成交量
            vol = int(avg_volume * (1 + np.random.randn() * 0.3))
            vol = max(vol, 1)

            rows.append({
                "open": op, "high": high, "low": low,
                "close": new_close, "volume": vol,
                "trade_date": ts,
            })
            cur_close = new_close

        pred_df = pd.DataFrame(rows)
        # Kronos 返回的索引是 trade_date
        pred_df.index = pd.to_datetime(pred_df["trade_date"])
        pred_df = pred_df.drop(columns=["trade_date"])
        return pred_df


# 全局单例
kronos_service = KronosService()