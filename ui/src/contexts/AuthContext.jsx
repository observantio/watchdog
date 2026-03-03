import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useNavigate } from "react-router-dom";
import PropTypes from "prop-types";
import * as api from "../api";

const AuthContext = createContext(null);

const OIDC_STATE_KEY = "oidc_state";
const OIDC_NONCE_KEY = "oidc_nonce";
const OIDC_TX_KEY = "oidc_tx";
const OIDC_CODE_VERIFIER_KEY = "oidc_code_verifier";

const OIDC_REDIRECT_PATH = "/auth/callback";
const getOidcRedirectUri = () =>
  `${globalThis.location.origin}${OIDC_REDIRECT_PATH}`;

const resolveActiveOrgId = (userData) => {
  const keys = userData?.api_keys || [];
  const active =
    keys.find((k) => k.is_enabled) || keys.find((k) => k.is_default);
  return active?.key || userData?.org_id || "";
};

const clearOidcSession = () => {
  sessionStorage.removeItem(OIDC_STATE_KEY);
  sessionStorage.removeItem(OIDC_NONCE_KEY);
  sessionStorage.removeItem(OIDC_TX_KEY);
  sessionStorage.removeItem(OIDC_CODE_VERIFIER_KEY);
};

const randomToken = (length = 64) => {
  const chars =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~";
  if (!globalThis.crypto?.getRandomValues)
    return `${Date.now()}-${Math.random()}`;
  const bytes = new Uint8Array(length);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => chars[b % chars.length]).join("");
};

const pkceChallengeFromVerifier = async (verifier) => {
  if (!globalThis.crypto?.subtle || !globalThis.TextEncoder) return null;
  const bytes = new globalThis.TextEncoder().encode(verifier);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  const b64 = globalThis.btoa(String.fromCharCode(...new Uint8Array(digest)));
  return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
};

const clearLegacyGrafanaCookie = () => {
  if (typeof document === "undefined") return;
  document.cookie = "beobservant_token=; Path=/; Max-Age=0; SameSite=Lax";
};

const isOnOidcCallback = () =>
  globalThis.location.pathname === OIDC_REDIRECT_PATH;

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);

  const [authMode, setAuthMode] = useState({
    provider: "local",
    oidc_enabled: false,
    password_enabled: true,
    registration_enabled: true,
    oidc_scopes: "openid profile email",
  });
  const [authModeLoading, setAuthModeLoading] = useState(true);
  const [loading, setLoading] = useState(true);

  const navigate = useNavigate();

  useEffect(() => {
    api.setAuthToken(token || null);
  }, [token]);

  const loadAuthMode = useCallback(async () => {
    setAuthModeLoading(true);
    try {
      const mode = await api.getAuthMode();
      setAuthMode(mode);
      return mode;
    } catch {
      const fallback = {
        provider: "local",
        oidc_enabled: false,
        password_enabled: true,
        registration_enabled: true,
        oidc_scopes: "openid profile email",
      };
      setAuthMode(fallback);
      return fallback;
    } finally {
      setAuthModeLoading(false);
    }
  }, []);

  const loadUser = useCallback(async () => {
    try {
      const [userData, apiKeys] = await Promise.all([
        api.getCurrentUserNoRedirect(),
        api.listApiKeys().catch(() => null),
      ]);
      const mergedUser = {
        ...userData,
        api_keys: Array.isArray(apiKeys) ? apiKeys : (userData?.api_keys || []),
      };
      setUser(mergedUser);
      api.setUserOrgIds(resolveActiveOrgId(mergedUser));
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAuthMode();
    loadUser();
  }, [loadAuthMode, loadUser]);

  const refreshUser = useCallback(async () => {
    try {
      const [userData, apiKeys] = await Promise.all([
        api.getCurrentUser(),
        api.listApiKeys().catch(() => null),
      ]);
      const mergedUser = {
        ...userData,
        api_keys: Array.isArray(apiKeys) ? apiKeys : (userData?.api_keys || []),
      };
      setUser(mergedUser);
      api.setUserOrgIds(resolveActiveOrgId(mergedUser));
    } catch (e) {
      console.error("Failed to refresh user:", e);
      setUser(null);
    }
  }, []);

  const login = useCallback(
    async (username, password, mfa_code) => {
      const res = await api.login(username, password, mfa_code);
      const accessToken = res?.access_token || null;
      setToken(accessToken);
      api.setAuthToken(accessToken);
      await refreshUser();
      return res;
    },
    [refreshUser],
  );

  const startOIDCLogin = useCallback(async () => {
    const state =
      globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    const nonce =
      globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    const verifier = randomToken(96);
    const challenge = await pkceChallengeFromVerifier(verifier);

    sessionStorage.setItem(OIDC_STATE_KEY, state);
    sessionStorage.setItem(OIDC_NONCE_KEY, nonce);
    sessionStorage.setItem(OIDC_CODE_VERIFIER_KEY, verifier);

    const redirectUri = getOidcRedirectUri();
    const resp = await api.getOIDCAuthorizeUrl(redirectUri, {
      state,
      nonce,
      code_challenge: challenge,
      code_challenge_method: challenge ? "S256" : null,
    });

    if (!resp?.authorization_url)
      throw new Error("OIDC authorization URL was not returned by the server");
    if (!resp?.transaction_id)
      throw new Error("OIDC transaction was not returned by the server");

    sessionStorage.setItem(OIDC_TX_KEY, resp.transaction_id);
    if (resp?.state) sessionStorage.setItem(OIDC_STATE_KEY, resp.state);

    globalThis.location.href = resp.authorization_url;
  }, []);

  const finishOIDCLogin = useCallback(
    async ({ code, state }) => {
      const expectedState = sessionStorage.getItem(OIDC_STATE_KEY);
      const txId = sessionStorage.getItem(OIDC_TX_KEY);
      const verifier = sessionStorage.getItem(OIDC_CODE_VERIFIER_KEY);

      if (!code) throw new Error("Missing OIDC authorization code");
      if (!state || !expectedState || state !== expectedState)
        throw new Error("Invalid OIDC state");
      if (!txId) throw new Error("Missing OIDC transaction");

      const redirectUri = getOidcRedirectUri();
      const resp = await api.exchangeOIDCCode(code, redirectUri, {
        state,
        transaction_id: txId,
        code_verifier: verifier,
      });

      const accessToken = resp?.access_token || null;

      clearOidcSession();
      setToken(accessToken);
      api.setAuthToken(accessToken);

      await loadUser();
      return resp;
    },
    [loadUser],
  );

  const register = useCallback(async (username, email, password, fullName) => {
    return await api.register(username, email, password, fullName);
  }, []);

  const clearSession = useCallback(() => {
    setToken(null);
    setUser(null);
    api.setAuthToken(null);
    clearLegacyGrafanaCookie();
    clearOidcSession();
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {}
    clearSession();
  }, [clearSession]);

  const updateUser = useCallback((userData) => {
    setUser(userData);
    api.setUserOrgIds(resolveActiveOrgId(userData));
  }, []);

  const hasPermission = useCallback(
    (permission) => user?.permissions?.includes(permission) || false,
    [user?.permissions],
  );

  const value = useMemo(
    () => ({
      user,
      token,
      authMode,
      authModeLoading,
      loading,
      isAuthenticated: !!user,
      hasPermission,
      loadAuthMode,
      refreshUser,
      loadUser,
      login,
      startOIDCLogin,
      finishOIDCLogin,
      register,
      logout,
      updateUser,
      clearSession,
    }),
    [
      user,
      token,
      authMode,
      authModeLoading,
      loading,
      hasPermission,
      loadAuthMode,
      refreshUser,
      loadUser,
      login,
      startOIDCLogin,
      finishOIDCLogin,
      register,
      logout,
      updateUser,
      clearSession,
    ],
  );

  useEffect(() => {
    const handler = (e) => {
      if (e?.detail?.status !== 401) return;
      if (isOnOidcCallback()) return;
      clearSession();
      navigate("/login", { replace: true });
    };

    globalThis.addEventListener("api-error", handler);
    globalThis.addEventListener("session-expired", handler);
    return () => {
      globalThis.removeEventListener("api-error", handler);
      globalThis.removeEventListener("session-expired", handler);
    };
  }, [clearSession, navigate]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

AuthProvider.propTypes = { children: PropTypes.node.isRequired };

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
