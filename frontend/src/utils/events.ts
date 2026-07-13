// Convention : toute mutation qui peut changer un badge de la sidebar
// (soumissions, remboursements, budget) appelle notifyBadgesChanged().
export const BADGES_CHANGED = "openflow:badges-changed";

export function notifyBadgesChanged() {
  window.dispatchEvent(new Event(BADGES_CHANGED));
}
