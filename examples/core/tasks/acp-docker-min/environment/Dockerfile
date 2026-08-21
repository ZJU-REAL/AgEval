# The official base already bakes the ACP entries; this task only adds its
# own dependency, which proves the recipe is honoured without a reinstall.
FROM ageval-attempt:base

USER root
RUN printf 'ageval docker box\n' > /etc/ageval-box-marker
USER ageval
