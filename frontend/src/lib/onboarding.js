/** Persistent first-run dismiss flags (localStorage). */

export const ONBOARD = {
  skipLanding: 'edge-skip-landing-v1',
  tipRegistry: 'edge-tip-registry-v1',
  tipWatch: 'edge-tip-watch-v1',
};

export function isOnboardingDismissed(key) {
  try {
    return localStorage.getItem(key) === '1';
  } catch {
    return false;
  }
}

export function dismissOnboarding(key) {
  try {
    localStorage.setItem(key, '1');
  } catch {
    /* private mode / quota */
  }
}

export function clearOnboardingFlag(key) {
  try {
    localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}
