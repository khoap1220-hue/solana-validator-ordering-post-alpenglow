FROM python:3.11-slim

WORKDIR /workspace
COPY scripts/pilots/superteam_01_agave_prio_graph_simulator.py /workspace/scripts/pilots/superteam_01_agave_prio_graph_simulator.py
COPY tests/test_superteam_breakthrough_bounties.py /workspace/tests/test_superteam_breakthrough_bounties.py
COPY data/deliverables/superteam_01_inside_the_block/ /workspace/data/deliverables/superteam_01_inside_the_block/

ENV PYTHONPATH=/workspace
CMD ["sh", "-c", "python -m unittest discover -s tests -p 'test_*.py' -v && python scripts/pilots/superteam_01_agave_prio_graph_simulator.py"]
