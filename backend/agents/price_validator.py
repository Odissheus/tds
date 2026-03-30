"""
Price Validator Agent - validates promotions before DB commit.
Uses Redis to persist stats across Celery worker and web processes.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import redis

from backend.config import settings

logger = logging.getLogger("tds.agent.price_validator")

REDIS_KEY = "tds:validation_stats"


def _get_redis():
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


class PriceValidator:
    PRICE_RANGES = {
        "smartphone": (150, 2500),
        "hearable": (20, 500),
        "wearable": (50, 800),
        "accessory": (5, 300),
        "bundle": (100, 3000),
    }

    MAX_DISCOUNT = {
        "smartphone": 0.55,
        "hearable": 0.60,
        "wearable": 0.60,
        "accessory": 0.70,
        "bundle": 0.65,
    }

    def __init__(self):
        self._local_stats = self._empty_stats()

    @staticmethod
    def _empty_stats():
        return {
            "total_validated": 0,
            "total_rejected": 0,
            "rejections_by_reason": {},
            "rejections_by_retailer": {},
            "last_scrape": None,
        }

    @property
    def stats(self) -> dict:
        """Read stats from Redis (cross-process)."""
        try:
            r = _get_redis()
            raw = r.get(REDIS_KEY)
            if raw:
                data = json.loads(raw)
            else:
                data = self._local_stats
        except Exception:
            data = self._local_stats

        total = data["total_validated"] + data["total_rejected"]
        rate = (data["total_rejected"] / total * 100) if total > 0 else 0.0
        return {
            "last_scrape": data.get("last_scrape"),
            "total_validated": data["total_validated"],
            "total_rejected": data["total_rejected"],
            "rejection_rate": f"{rate:.1f}%",
            "rejections_by_reason": data.get("rejections_by_reason", {}),
            "rejections_by_retailer": data.get("rejections_by_retailer", {}),
        }

    def reset_stats(self):
        self._local_stats = self._empty_stats()
        self._local_stats["last_scrape"] = datetime.now(timezone.utc).isoformat()
        self._flush_to_redis()

    def _flush_to_redis(self):
        try:
            r = _get_redis()
            r.set(REDIS_KEY, json.dumps(self._local_stats), ex=86400 * 7)
        except Exception as e:
            logger.warning("Could not write validation stats to Redis: %s", e)

    def validate(self, prezzo_promo: float, prezzo_originale: Optional[float],
                 category: str, listino: Optional[float], retailer: str = "") -> tuple:
        """Returns (is_valid, reason)."""
        price = prezzo_promo
        original = prezzo_originale

        # 1. Absolute price range
        min_p, max_p = self.PRICE_RANGES.get(category, (10, 3000))
        if not (min_p <= price <= max_p):
            reason = f"Prezzo EUR{price} fuori range {category} ({min_p}-{max_p})"
            self._record_rejection(reason, retailer)
            return False, reason

        # 2. Discount vs listino
        if listino and listino > 0:
            discount_vs_listino = (listino - price) / listino
            max_disc = self.MAX_DISCOUNT.get(category, 0.60)
            if discount_vs_listino > max_disc:
                reason = f"Sconto {discount_vs_listino:.1%} vs listino EUR{listino} supera soglia {max_disc:.0%}"
                self._record_rejection(reason, retailer)
                return False, reason

        # 3. Discount vs original crossed-out price
        if original and original > 0 and original > price:
            discount_vs_original = (original - price) / original
            if discount_vs_original > 0.75:
                reason = f"Sconto {discount_vs_original:.1%} vs prezzo barrato sospetto"
                self._record_rejection(reason, retailer)
                return False, reason

        # 4. Original < promo
        if original and original < price:
            reason = f"Prezzo originale EUR{original} < prezzo promo EUR{price}"
            self._record_rejection(reason, retailer)
            return False, reason

        # 5. Flagship sanity check
        if category == "smartphone" and listino and listino > 800:
            if price < listino * 0.35:
                reason = f"Prezzo EUR{price} troppo basso per flagship EUR{listino}"
                self._record_rejection(reason, retailer)
                return False, reason

        self._local_stats["total_validated"] += 1
        # Flush periodically (every 10 validations)
        if self._local_stats["total_validated"] % 10 == 0:
            self._flush_to_redis()
        return True, "OK"

    def _record_rejection(self, reason: str, retailer: str):
        self._local_stats["total_rejected"] += 1
        if "fuori range" in reason:
            key = "Prezzo fuori range"
        elif "listino" in reason or "soglia" in reason:
            key = "Sconto vs listino supera soglia"
        elif "barrato" in reason:
            key = "Sconto vs prezzo barrato sospetto"
        elif "originale" in reason and "<" in reason:
            key = "Prezzo originale < promo"
        elif "troppo basso" in reason:
            key = "Prezzo troppo basso per flagship"
        else:
            key = reason[:50]
        self._local_stats["rejections_by_reason"][key] = self._local_stats["rejections_by_reason"].get(key, 0) + 1
        r = retailer.strip().lower() if retailer else "unknown"
        self._local_stats["rejections_by_retailer"][r] = self._local_stats["rejections_by_retailer"].get(r, 0) + 1
        # Flush to Redis on every rejection
        self._flush_to_redis()


# Singleton
price_validator = PriceValidator()
