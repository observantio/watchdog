import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useToast } from "../contexts/ToastContext";
import * as api from "../api";
import { Card, Spinner } from "../components/ui";
import PasswordLoginForm from "../components/auth/PasswordLoginForm";
import OIDCLoginButton from "../components/auth/OIDCLoginButton";
import { OIDC_PROVIDER_LABEL } from "../utils/constants";
import { copyToClipboard as clipboardCopy } from "../utils/helpers";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mfaRequired, setMfaRequired] = useState(false);
  const [mfaCode, setMfaCode] = useState("");
  const [useRecoveryCode, setUseRecoveryCode] = useState(false);
  const [showMfaSetup, setShowMfaSetup] = useState(false);
  const [setupStep, setSetupStep] = useState(0);
  const [setupLoading, setSetupLoading] = useState(false);
  const [setupSecret, setSetupSecret] = useState("");
  const [setupQrUrl, setSetupQrUrl] = useState("");
  const [setupCode, setSetupCode] = useState("");
  const [verifiedSetupCode, setVerifiedSetupCode] = useState("");
  const [setupRecoveryCodes, setSetupRecoveryCodes] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [oidcLoading, setOidcLoading] = useState(false);
  const {
    login,
    startOIDCLogin,
    authMode,
    authModeLoading,
    isAuthenticated,
    loading: authLoading,
  } = useAuth();
  const navigate = useNavigate();
  useEffect(() => {
    if (!authLoading && isAuthenticated) {
      navigate("/", { replace: true });
    }
  }, [authLoading, isAuthenticated, navigate]);

  const hasOIDC = Boolean(authMode?.oidc_enabled);
  const hasPassword = Boolean(authMode?.password_enabled);
  const showDivider = hasOIDC && hasPassword;
  const showLoginLogo = !showMfaSetup && !mfaRequired;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (!hasPassword) {
      setError("Password login is disabled. Use Single Sign-On.");
      return;
    }

    if (!username.trim()) {
      setError("Username is required");
      return;
    }
    if (!password) {
      setError("Password is required");
      return;
    }

    setLoading(true);
    try {
      await login(username.trim(), password);
      navigate("/");
    } catch (err) {
      if (err?.status === 401 && err?.body?.detail === "MFA required") {
        setMfaRequired(true);
        setUseRecoveryCode(false);
        setError("");
        return;
      }
      const challenge =
        err?.body?.detail && typeof err.body.detail === "object"
          ? err.body.detail
          : err?.body && typeof err.body === "object"
            ? err.body
            : null;

      if (err?.status === 401 && challenge?.mfa_setup_required) {
        const setupToken = challenge.setup_token;
        try {
          api.setSetupToken(setupToken);
        } catch (_) {}
        setSetupStep(0);
        setSetupSecret("");
        setSetupQrUrl("");
        setSetupCode("");
        setSetupRecoveryCodes([]);
        setShowMfaSetup(true);
        return;
      }
      setError("Invalid username or password. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyMfa = async (e) => {
    e.preventDefault();
    setError("");
    if (!mfaCode) {
      setError(
        useRecoveryCode
          ? "Enter one of your recovery codes to continue"
          : "Enter the authentication code from your authenticator app to continue",
      );
      return;
    }
    setLoading(true);
    try {
      await login(username.trim(), password, mfaCode);
      navigate("/");
    } catch (err) {
      setError(
        err?.body?.detail ||
          err?.message ||
          "Invalid authenticator or recovery code, or your session expired.",
      );
    } finally {
      setLoading(false);
    }
  };

  const handleOIDCLogin = async () => {
    setError("");
    setOidcLoading(true);
    try {
      await startOIDCLogin();
    } catch (err) {
      setError(err?.message || "Unable to start Single Sign-On");
      setOidcLoading(false);
    }
  };

  const startMfaSetup = async () => {
    setError("");
    setSetupLoading(true);
    try {
      const payload = await api.enrollMFA();
      setSetupSecret(payload.secret);
      setSetupQrUrl(payload.otpauth_url);
      setSetupStep(1);
    } catch (err) {
      setError(
        err?.body?.detail || err?.message || "Failed to start MFA setup",
      );
    } finally {
      setSetupLoading(false);
    }
  };

  const toast = useToast();

  const verifyMfaSetup = async (e) => {
    e.preventDefault();
    setError("");
    if (!setupCode) {
      setError("Authentication code is required");
      return;
    }

    setSetupLoading(true);
    try {
      const res = await api.verifyMFA(setupCode);
      setSetupRecoveryCodes(res?.recovery_codes || []);
      setVerifiedSetupCode(setupCode);
      setSetupStep(2);
    } catch (err) {
      setError(
        err?.body?.detail || err?.message || "Failed to verify MFA code",
      );
    } finally {
      setSetupLoading(false);
    }
  };

  const cancelMfaSetup = () => {
    api.clearSetupToken();
    setShowMfaSetup(false);
    setSetupStep(0);
    setSetupSecret("");
    setSetupQrUrl("");
    setSetupCode("");
    setVerifiedSetupCode("");
    setSetupRecoveryCodes([]);
  };

  const providerLabel = hasOIDC ? OIDC_PROVIDER_LABEL : "Single Sign-On";

  return (
    <div className="min-h-screen flex items-center justify-center bg-sre-bg p-4">
      <Card className="w-full max-w-md">
        <div className="text-center mb-8">
          {showLoginLogo && (
            <img
              src="/favicon.png"
              alt="Watchdog logo"
              className="mx-auto  w-43 h-43 dark:filter dark:invert"
            />
          )}
          <h1 className="text-3xl font-bold text-sre-text mb-2">
            Watchdog
          </h1>
          <p className="font-lg">
            Observing your entire infrastructure
          </p>
        </div>

        {error && (
          <div
            className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2 text-red-500 text-sm"
            role="alert"
          >
            <span className="material-icons text-sm">error_outline</span>
            {error}
          </div>
        )}

        {authModeLoading && (
          <div className="flex items-center justify-center py-6">
            <Spinner size="md" />
          </div>
        )}

        {!authModeLoading && hasOIDC && (
          <OIDCLoginButton
            loading={oidcLoading}
            onClick={handleOIDCLogin}
            providerLabel={providerLabel}
          />
        )}

        {!authModeLoading && showDivider && (
          <div className="my-4 text-center text-xs text-sre-text-muted uppercase tracking-wide">
            or use password
          </div>
        )}

        {!authModeLoading &&
          hasPassword &&
          (showMfaSetup ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between text-xs text-sre-text-muted">
                <span>Step {Math.min(setupStep + 1, 3)} of 3</span>
                <button
                  type="button"
                  className="underline"
                  onClick={cancelMfaSetup}
                >
                  Cancel
                </button>
              </div>

              {setupStep === 0 && (
                <div className="space-y-4 animate-fade-in">
                  <h2 className="text-lg font-semibold text-sre-text">
                    Set up two-factor authentication
                  </h2>
                  <p className="text-sm text-sre-text-muted">
                    Your account requires MFA before you can continue. Click
                    below to generate your authenticator setup.
                  </p>
                  <button
                    type="button"
                    className="w-full px-4 py-2 bg-sre-primary text-white rounded"
                    onClick={startMfaSetup}
                    disabled={setupLoading}
                  >
                    {setupLoading ? "Preparing setup..." : "Start MFA setup"}
                  </button>
                </div>
              )}

              {setupStep === 1 && (
                <form
                  onSubmit={verifyMfaSetup}
                  className="space-y-4 animate-fade-in"
                >
                  <h2 className="text-lg font-semibold text-sre-text">
                    Verify your authenticator code
                  </h2>
                  {setupQrUrl && (
                    <div className="flex justify-center">
                      <img
                        src={`https://api.qrserver.com/v1/create-qr-code/?data=${encodeURIComponent(setupQrUrl)}&size=200x200`}
                        alt="Authenticator QR"
                      />
                    </div>
                  )}
                  {setupSecret && (
                    <div>
                      <label className="block text-xs text-sre-text-muted mb-1">
                        Manual secret
                      </label>
                      <input
                        type="text"
                        value={setupSecret}
                        readOnly
                        className="w-full px-3 py-2 bg-sre-bg border border-sre-border rounded text-sre-text"
                      />
                    </div>
                  )}
                  <div>
                    <label
                      htmlFor="setupMfa"
                      className="block text-sm font-medium text-sre-text mb-1"
                    >
                      Authentication code
                    </label>
                    <input
                      id="setupMfa"
                      type="text"
                      value={setupCode}
                      onChange={(e) => setSetupCode(e.target.value)}
                      placeholder="Enter 6-digit code"
                      className="w-full px-3 py-2 bg-sre-bg border border-sre-border rounded text-sre-text"
                      autoFocus
                    />
                  </div>

                  <div className="text-sm text-sre-text-muted">
                    After verification you'll be shown recovery codes — make
                    sure to copy or download them. You will need these if you
                    lose access to your authenticator.
                  </div>

                  <button
                    type="submit"
                    className="w-full px-4 py-2 bg-sre-primary text-white rounded"
                    disabled={setupLoading}
                  >
                    {setupLoading ? "Verifying..." : "Verify"}
                  </button>
                </form>
              )}

              {setupStep === 2 && (
                <div className="space-y-4 animate-fade-in">
                  <h2 className="text-lg font-semibold text-sre-text">
                    Recovery codes — save these now
                  </h2>
                  <p className="text-sm text-sre-text-muted">
                    These recovery codes are shown only once. Copy or download
                    them and store them securely.
                  </p>

                  <div className="p-3 bg-sre-bg border border-sre-border rounded">
                    <div className="grid grid-cols-2 gap-2 mt-2">
                      {setupRecoveryCodes.map((code) => (
                        <div
                          key={code}
                          className="p-2 bg-sre-surface border border-sre-border rounded font-mono text-xs text-sre-text text-center"
                        >
                          {code}
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <button
                      type="button"
                      className="px-3 py-2 bg-sre-surface border rounded"
                      onClick={async () => {
                        const txt = setupRecoveryCodes.join("\n");
                        const ok = await clipboardCopy(txt);
                        if (ok) toast.success("Recovery codes copied");
                        else toast.error("Unable to copy");
                      }}
                    >
                      Copy codes
                    </button>

                    <button
                      type="button"
                      className="px-3 py-2 bg-sre-surface border rounded"
                      onClick={() => {
                        (async () => {
                          const { downloadFile } =
                            await import("../utils/helpers");
                          downloadFile(
                            setupRecoveryCodes.join("\n"),
                            "watchdog-recovery-codes.txt",
                            "text/plain",
                          );
                          toast.success("Recovery codes downloaded");
                        })();
                      }}
                    >
                      Download
                    </button>

                    <div className="flex-1" />

                    <button
                      type="button"
                      className="px-4 py-2 bg-sre-primary text-white rounded"
                      disabled={
                        !verifiedSetupCode ||
                        setupRecoveryCodes.length === 0 ||
                        setupLoading
                      }
                      onClick={async () => {
                        setSetupLoading(true);
                        setError("");
                        try {
                          await login(
                            username.trim(),
                            password,
                            verifiedSetupCode,
                          );
                          api.clearSetupToken();
                          setShowMfaSetup(false);
                          setSetupStep(0);
                          setSetupCode("");
                          setVerifiedSetupCode("");
                          setSetupRecoveryCodes([]);
                          navigate("/");
                        } catch (err) {
                          setError(
                            err?.body?.detail || err?.message || "Login failed",
                          );
                        } finally {
                          setSetupLoading(false);
                        }
                      }}
                    >
                      {setupLoading ? (
                        <span className="flex items-center gap-2">
                          <Spinner size="sm" />
                          Logging in...
                        </span>
                      ) : (
                        "Login"
                      )}
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : mfaRequired ? (
            <form onSubmit={handleVerifyMfa} className="space-y-4">
              <div>
                <label
                  htmlFor="mfa"
                  className="block text-sm font-medium text-sre-text mb-1"
                >
                  {useRecoveryCode ? "Recovery code" : "Authentication code"}
                </label>
                <input
                  id="mfa"
                  type="text"
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  placeholder={
                    useRecoveryCode
                      ? "Enter recovery code"
                      : "Enter 6-digit code"
                  }
                  className="w-full px-3 py-2 bg-sre-bg border border-sre-border rounded text-sre-text"
                  autoFocus
                />
                <p className="text-xs text-sre-text-muted mt-2">
                  {useRecoveryCode
                    ? "Recovery codes are single-use. Enter one exactly as saved."
                    : "Use the code from your authenticator app, or switch to a recovery code if unavailable."}
                </p>
              </div>
              <button
                type="button"
                className="text-xs text-sre-primary underline"
                onClick={() => {
                  setUseRecoveryCode((prev) => !prev);
                  setMfaCode("");
                  setError("");
                }}
              >
                {useRecoveryCode
                  ? "Use authenticator code instead"
                  : "Use recovery code instead"}
              </button>
              <div className="flex gap-2 justify-end">
                <button
                  type="submit"
                  className="px-4 py-2 bg-sre-primary text-white rounded"
                  disabled={loading}
                >
                  {loading ? "Verifying..." : "Verify"}
                </button>
                <button
                  type="button"
                  className="px-4 py-2 bg-sre-surface border rounded"
                  onClick={() => {
                    setMfaRequired(false);
                    setUseRecoveryCode(false);
                    setMfaCode("");
                  }}
                >
                  Back
                </button>
              </div>
            </form>
          ) : (
            <PasswordLoginForm
              username={username}
              password={password}
              onUsernameChange={setUsername}
              onPasswordChange={setPassword}
              onSubmit={handleSubmit}
              loading={loading}
              disabled={oidcLoading}
            />
          ))}

        {!authModeLoading && !hasOIDC && !hasPassword && (
          <p className="text-sm text-red-500 text-center">
            Authentication is not configured. Contact your administrator.
          </p>
        )}

        <p className="text-xs text-sre-text-muted text-center mt-6">
          Contact your administrator if you need access or have forgotten your
          credentials.
        </p>
      </Card>
    </div>
  );
}
