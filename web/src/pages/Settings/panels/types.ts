// TODO: type properly — depends on backend preferences shape
export interface Preferences {
  agent_preference?: Record<string, unknown>;
  other_preference?: Record<string, unknown>;
}
