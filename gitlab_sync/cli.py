#!/usr/bin/env python
import logging

import click
import gitlab_sync
import gitlab_sync.conductor
from gitlab_sync.config import find_and_load_config


@click.group()
@click.option("-v", "--verbose", count=True)
@click.pass_context
def main(ctx, verbose):
    log_level = [logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG][
        min(verbose, 3)
    ]
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S%z",
        level=log_level,
    )
    gitlab_sync.tee_git = log_level == logging.DEBUG

    config = find_and_load_config()
    ctx.obj = config


@main.command("local-update", short_help="synchronise managed repositories")
@click.pass_context
def local_update(ctx):
    run_configs = ctx.obj
    # XXX: more like mirror really, and that should be a config only thing,
    #  not something you choose on a run by run basis…
    # XXX: could return projectless repos (new) and missing repos? maybe
    # guard against deleting all projects if restoring config from backup
    # but not repo directory
    for config in run_configs.values():
        gitlab_sync.conductor.backup(config)
        # pull in changes from GitLab
        #  * fetch remote
        #  * update remote head
        #  * what if branches are ahead or diverged? - only care about origin/HEAD
        # gitlab_sync.conductor.pull_changes()
        # XXX: push means have to consider various heads changing
        # push out changes to GitLab
        #  * push branches - config to disallow pushing to remote HEAD
        #  * create new projects (what happens if no permission, manually created?)
        # gitlab_sync.conductor.push_changes()


if __name__ == "__main__":
    main()
