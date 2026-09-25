"""Where this lab reads from and writes to.

Nothing written by a run belongs inside the checkout. `market_core.paths`
hands out the directory for that, keyed on an application name, because
the same helper was written twice under two different environment
variable conventions before it moved into the shared package.

Every value here is overridable by environment variable. The archive is
about to stop being a SQLite file on this machine and become Postgres on
a Linux box, so nothing may assume the path, the engine or the network
location.
"""
import os

from market_core import paths

APP = "strategy-lab"

#: Connection string for the archive. `sqlite:///<path>` today. When the
#: archive moves this becomes `postgresql://host/db` and nothing above
#: the backend layer changes.
ARCHIVE_URL = os.environ.get(
    "STRATEGY_LAB_ARCHIVE_URL",
    "sqlite:///" + os.path.expanduser("~/market-data/sharadar.db"),
)


def data_dir():
    """The directory for everything this lab writes."""
    return paths.data_dir(APP)


def data_file(name, env=None):
    """Full path for one file this lab writes."""
    return paths.data_file(APP, name, env=env)


def results_db():
    """The results database: every run, its code version and its config."""
    return data_file("results.db", env="STRATEGY_LAB_RESULTS_DB")


def panel_dir():
    """Derived panels and saved output, written as Parquet."""
    return os.path.join(data_dir(), "panels")


def recorder_dir():
    """Where the forward recorders write. Perishable data lands here."""
    return os.path.join(data_dir(), "recordings")


def ensure_dirs():
    for d in (data_dir(), panel_dir(), recorder_dir()):
        os.makedirs(d, exist_ok=True)
    return data_dir()
