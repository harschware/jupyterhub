"""Database utilities for JupyterHub"""
# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

# Based on pgcontents.utils.migrate, used under the Apache license.

from contextlib import contextmanager
from datetime import datetime
import os
import shutil
from subprocess import check_call
import sys
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine

from . import orm

_here = os.path.abspath(os.path.dirname(__file__))

ALEMBIC_INI_TEMPLATE_PATH = os.path.join(_here, 'alembic.ini')
ALEMBIC_DIR = os.path.join(_here, 'alembic')


def write_alembic_ini(alembic_ini='alembic.ini', db_url='sqlite:///jupyterhub.sqlite'):
    """Write a complete alembic.ini from our template.

    Parameters
    ----------

    alembic_ini: str
        path to the alembic.ini file that should be written.
    db_url: str
        The SQLAlchemy database url, e.g. `sqlite:///jupyterhub.sqlite`.
    """
    with open(ALEMBIC_INI_TEMPLATE_PATH) as f:
        alembic_ini_tpl = f.read()

    with open(alembic_ini, 'w') as f:
        f.write(
            alembic_ini_tpl.format(
                alembic_dir=ALEMBIC_DIR,
                # If there are any %s in the URL, they should be replaced with %%, since ConfigParser
                # by default uses %() for substitution. You'll get %s in your URL when you have usernames
                # with special chars (such as '@') that need to be URL encoded. URL Encoding is done with %s.
                # YAY for nested templates?
                db_url=str(db_url).replace('%', '%%'),
            )
        )


@contextmanager
def _temp_alembic_ini(db_url):
    """Context manager for temporary JupyterHub alembic directory

    Temporarily write an alembic.ini file for use with alembic migration scripts.

    Context manager yields alembic.ini path.

    Parameters
    ----------

    db_url: str
        The SQLAlchemy database url, e.g. `sqlite:///jupyterhub.sqlite`.

    Returns
    -------

    alembic_ini: str
        The path to the temporary alembic.ini that we have created.
        This file will be cleaned up on exit from the context manager.
    """
    with TemporaryDirectory() as td:
        alembic_ini = os.path.join(td, 'alembic.ini')
        write_alembic_ini(alembic_ini, db_url)
        yield alembic_ini


def upgrade(db_url, revision='head'):
    """Upgrade the given database to revision.

    db_url: str
        The SQLAlchemy database url, e.g. `sqlite:///jupyterhub.sqlite`.
    revision: str [default: head]
        The alembic revision to upgrade to.
    """
    with _temp_alembic_ini(db_url) as alembic_ini:
        check_call(
            ['alembic', '-c', alembic_ini, 'upgrade', revision]
        )


def backup_db_file(db_file, log=None):
    """Backup a database file if it exists"""
    timestamp = datetime.now().strftime('.%Y-%m-%d-%H%M%S')
    backup_db_file = db_file + timestamp
    for i in range(1, 10):
        if not os.path.exists(backup_db_file):
            break
        backup_db_file = '{}.{}.{}'.format(db_file, timestamp, i)
    #
    if os.path.exists(backup_db_file):
        raise OSError("backup db file already exists: %s" % backup_db_file)
    if log:
        log.info("Backing up %s => %s", db_file, backup_db_file)
    shutil.copy(db_file, backup_db_file)


def upgrade_if_needed(db_url, backup=True, log=None):
    """Upgrade a database if needed

    If the database is sqlite, a backup file will be created with a timestamp.
    Other database systems should perform their own backups prior to calling this.
    """
    # run check-db-revision first
    engine = create_engine(db_url)
    try:
        orm.check_db_revision(engine)
    except orm.DatabaseSchemaMismatch:
        # ignore mismatch error because that's what we are here for!
        pass
    else:
        # nothing to do
        return
    log.info("Upgrading %s", db_url)
    # we need to upgrade, backup the database
    if backup and db_url.startswith('sqlite:///'):
        db_file = db_url.split(':///', 1)[1]
        backup_db_file(db_file, log=log)
    upgrade(db_url)


def _alembic(*args):
    """Run an alembic command with a temporary alembic.ini"""
    with _temp_alembic_ini('sqlite:///jupyterhub.sqlite') as alembic_ini:
        check_call(
            ['alembic', '-c', alembic_ini] + list(args)
        )


if __name__ == '__main__':
    _alembic(*sys.argv[1:])
