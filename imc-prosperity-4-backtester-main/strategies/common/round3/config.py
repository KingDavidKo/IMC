HYDROGEL_PACK = "HYDROGEL_PACK"
VELVETFRUIT_EXTRACT = "VELVETFRUIT_EXTRACT"
ANCHOR_VOUCHERS = ("VEV_5100", "VEV_5200", "VEV_5300")

OPTION_TTE_YEARS = 5.0 / 365.0
DEFAULT_IV = 0.30
MIN_IV = 0.15
MAX_IV = 0.60


class LinearConfig:
    def __init__(
        self,
        limit: int,
        ema_alpha: float,
        inventory_skew_ticks: float,
        passive_size: int,
        taker_cap: int,
        take_edge: float,
        min_half_width: int,
    ) -> None:
        self.limit = limit
        self.ema_alpha = ema_alpha
        self.inventory_skew_ticks = inventory_skew_ticks
        self.passive_size = passive_size
        self.taker_cap = taker_cap
        self.take_edge = take_edge
        self.min_half_width = min_half_width
