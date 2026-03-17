from enum import StrEnum


class Environment(StrEnum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


class EventType(StrEnum):
    HEALTH = "health"
    TICK = "tick"
    QUOTE = "quote"
    TRADE = "trade"
    BAR = "bar"
    INDICATOR = "indicator"
    SIGNAL = "signal"
    ORDER_COMMAND = "order_command"
    ORDER_UPDATE = "order_update"
    TRADE_UPDATE = "trade_update"
    ERROR = "error"


class ServiceName(StrEnum):
    AUTH_SERVICE = "auth_service"
    MARKET_DATA_GATEWAY = "market_data_gateway"
    BAR_BUILDER = "bar_builder"
    INDICATOR_ENGINE = "indicator_engine"
    GAP_RECONCILER = "gap_reconciler"
    EXECUTION_SERVICE = "execution_service"
    RISK_SERVICE = "risk_service"
    STRATEGY_RUNTIME = "strategy_runtime"
    CHART_API = "chart_api"