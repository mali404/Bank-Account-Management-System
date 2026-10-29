# agentbank_gateway

Agent gateway: defense plugin host and taint-tracking interfaces (SPEC §5.4, §9, §19). D0 is the baseline. **M4** runs the six LangGraph agents through this gateway. **M6** adds D1-D10. The reference-model benign utility is 1.0 (`runner.BENIGN_UTILITY`), and those defenses do not refuse the 30 benign tasks under the careful user-sim.

Part of the [AgentBank-Sec Testbed](../../README.md). Apache-2.0.
