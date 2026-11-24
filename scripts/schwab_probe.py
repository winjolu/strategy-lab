"""What Schwab's market-data API actually serves, measured once, read-only.

Answers four questions and nothing else:

1. How far back SPY daily price history goes.
2. What one current SPY option chain carries: expirations, strikes, and which
   fields each contract has (bid, ask, volatility, greeks, open interest).
3. Whether any price history is served for an option contract.
4. How long the token lasts, from the token file the login writes.

The first run opens a browser for a Schwab login; the token is written to
SCHWAB_TOKEN_PATH, readable only by its owner, and reused until it expires.
Credentials come from the shared secrets file through market_core.secrets
and are never printed. Results go to the lab's data directory as JSON; no
order endpoint is called, and the app is registered for market data only.
"""
import datetime as dt
import json
import os
import sys
import warnings

from market_core import secrets

from lab import config

warnings.filterwarnings("ignore", category=DeprecationWarning)
SYMBOL = "SPY"
REQUIRED = ("SCHWAB_APP_KEY", "SCHWAB_APP_SECRET", "SCHWAB_CALLBACK_URL", "SCHWAB_TOKEN_PATH")


def client():
    from schwab import auth
    secrets.load()
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"not set in the shared secrets file: {missing}")
    token_path = os.path.expanduser(os.environ["SCHWAB_TOKEN_PATH"])
    os.umask(0o077)   # the library writes the token with default permissions
    c = auth.easy_client(
        api_key=os.environ["SCHWAB_APP_KEY"], app_secret=os.environ["SCHWAB_APP_SECRET"],
        callback_url=os.environ["SCHWAB_CALLBACK_URL"], token_path=token_path)
    os.chmod(token_path, 0o600)
    return c, token_path


def get(resp, what):
    if resp.status_code != 200:
        raise SystemExit(f"{what}: HTTP {resp.status_code}")
    return resp.json()


def price_history(c):
    body = get(c.get_price_history_every_day(
        SYMBOL, start_datetime=dt.datetime(1985, 1, 1)), "price history")
    candles = body.get("candles", [])
    days = [dt.datetime.fromtimestamp(x["datetime"] / 1000, dt.timezone.utc).date() for x in candles]
    return {"rows": len(candles), "first": str(min(days)) if days else None,
            "last": str(max(days)) if days else None,
            "fields": sorted(candles[0].keys()) if candles else []}


def option_chain(c):
    body = get(c.get_option_chain(SYMBOL, strike_count=10, include_underlying_quote=True), "option chain")
    out = {"status": body.get("status"), "underlying_price": body.get("underlyingPrice"),
           "is_delayed": body.get("isDelayed")}
    sample = None
    for side in ("callExpDateMap", "putExpDateMap"):
        exps = body.get(side, {})
        out[side] = {"expirations": len(exps),
                     "first": min(exps) if exps else None, "last": max(exps) if exps else None,
                     "contracts": sum(len(s) for s in exps.values())}
        if exps and sample is None:
            strikes = exps[min(exps)]
            sample = strikes[sorted(strikes, key=float)[len(strikes) // 2]][0]
    out["contract_fields"] = sorted(sample.keys()) if sample else []
    out["sample_contract"] = {k: sample.get(k) for k in (
        "symbol", "bid", "ask", "last", "volatility", "delta", "gamma", "theta", "vega",
        "openInterest", "totalVolume", "daysToExpiration", "quoteTimeInLong")} if sample else None
    return out, (sample or {}).get("symbol")


def option_history(c, contract):
    if not contract:
        return {"tried": False, "reason": "no contract in the chain"}
    resp = c.get_price_history_every_day(contract, start_datetime=dt.datetime.now() - dt.timedelta(days=30))
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    return {"tried": True, "contract": contract, "http": resp.status_code,
            "rows": len(body.get("candles", [])) if isinstance(body, dict) else 0,
            "empty": body.get("empty") if isinstance(body, dict) else None}


def token_life(token_path):
    with open(token_path) as fh:
        tok = json.load(fh)
    created = tok.get("creation_timestamp")
    inner = tok.get("token", {})
    return {"created": dt.datetime.fromtimestamp(created, dt.timezone.utc).isoformat() if created else None,
            "access_expires_in_s": inner.get("expires_in"),
            "refresh_note": "schwab-py treats the refresh token as good for 7 days from creation"}


def main():
    c, token_path = client()
    result = {"measured_at": dt.datetime.now(dt.timezone.utc).isoformat(), "symbol": SYMBOL}
    result["price_history"] = price_history(c)
    result["option_chain"], contract = option_chain(c)
    result["option_history"] = option_history(c, contract)
    result["token"] = token_life(token_path)
    path = config.data_file("schwab-probe.json")
    with open(path, "w") as fh:
        json.dump(result, fh, indent=1, default=str)
    print(json.dumps(result, indent=1, default=str))
    print(f"wrote {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
