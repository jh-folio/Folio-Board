import type { LegacyBridge } from "./legacyBridge";

export type AgentContextPatch = Record<string, unknown>;

const scopeContexts = new Map<string, AgentContextPatch>();
let activeScope = "";

declare global {
  interface Window {
    FolioAgent?: {
      currentContext?: AgentContextPatch;
    };
    FolioBridge?: LegacyBridge;
  }
}

function publish(context: AgentContextPatch) {
  const next = { ...context };
  window.FolioAgent = { ...(window.FolioAgent || {}), currentContext: next };
  return next;
}

export function setReactAgentContextScope(scope: string, context: AgentContextPatch = {}) {
  const next = { ...context };
  scopeContexts.set(scope, next);
  return activeScope === scope ? publish(next) : next;
}

export function patchReactAgentContextScope(scope: string, patch: AgentContextPatch = {}) {
  return setReactAgentContextScope(scope, { ...(scopeContexts.get(scope) || {}), ...patch });
}

export function resetReactAgentContextScope(scope: string) {
  scopeContexts.delete(scope);
  if (activeScope === scope) publish({});
}

export function activateReactAgentContextScope(scope: string, fallback: AgentContextPatch = {}) {
  activeScope = scope;
  if (!scopeContexts.has(scope)) scopeContexts.set(scope, { ...fallback });
  const next = { ...(scopeContexts.get(scope) || {}) };
  delete next.selectedText;
  delete next.visibleSection;
  scopeContexts.set(scope, next);
  return publish(next);
}

export function openReactAgentDock(context: AgentContextPatch = {}) {
  // A chart action belongs to its explicit message, not the whole screen or a
  // different conversation opened later. The bridge still receives the fact ID.
  const { chartMovement: _chartMovement, ...screenContext } = context;
  if (activeScope) patchReactAgentContextScope(activeScope, screenContext);
  else publish(screenContext);
  window.FolioBridge?.openAgentDock?.(context);
}
