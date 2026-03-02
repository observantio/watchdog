import { useEffect, useState } from "react";
import { getActiveAgents } from "../api";

export function useAgentActivity() {
  const [agentActivity, setAgentActivity] = useState([]);
  const [loadingAgents, setLoadingAgents] = useState(true);

  useEffect(() => {
    let active = true;

    (async () => {
      try {
        if (active) setLoadingAgents(true);
        const res = await getActiveAgents();
        if (active) setAgentActivity(Array.isArray(res) ? res : []);
      } catch (e) {
        void e;
        if (active) setAgentActivity([]);
      } finally {
        if (active) setLoadingAgents(false);
      }
    })();

    return () => {
      active = false;
    };
  }, []);

  return {
    agentActivity,
    loadingAgents,
  };
}
