import PropTypes from "prop-types";
import { Input, Select } from "../../ui";
import HelpTooltip from "../../HelpTooltip";

function setEmailConfig(formData, setFormData, updates) {
  setFormData({
    ...formData,
    config: {
      ...formData.config,
      ...updates,
    },
  });
}

export default function EmailChannelFields({ formData, setFormData }) {
  const config = formData.config || {};
  const provider = config.emailProvider || config.email_provider || "smtp";
  const authType = config.smtpAuthType || config.smtp_auth_type || "password";

  return (
    <>
      <div>
        <label className="block text-sm font-medium text-sre-text mb-2">
          Email Address{" "}
          <HelpTooltip text="The email address where alert notifications will be sent." />
        </label>
        <Input
          type="email"
          value={config.to || ""}
          onChange={(e) =>
            setEmailConfig(formData, setFormData, { to: e.target.value })
          }
          placeholder="alerts@example.com"
          required
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-sre-text mb-2">
          Delivery Method{" "}
          <HelpTooltip text="Choose SMTP or API-based delivery provider." />
        </label>
        <Select
          value={provider}
          onChange={(e) =>
            setEmailConfig(formData, setFormData, {
              emailProvider: e.target.value,
              email_provider: e.target.value,
            })
          }
        >
          <option value="smtp">SMTP</option>
          <option value="sendgrid">SendGrid API</option>
          <option value="resend">Resend API</option>
        </Select>
      </div>

      <div>
        <label className="block text-sm font-medium text-sre-text mb-2">
          From address{" "}
          <HelpTooltip text="Sender address used in outgoing emails." />
        </label>
        <Input
          type="email"
          value={config.smtpFrom || config.smtp_from || config.from || ""}
          onChange={(e) =>
            setEmailConfig(formData, setFormData, {
              smtpFrom: e.target.value,
              smtp_from: e.target.value,
              from: e.target.value,
            })
          }
          placeholder="watchdog@example.com"
        />
      </div>

      {provider === "smtp" && (
        <>
          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">
              SMTP Server{" "}
              <HelpTooltip text="The SMTP server hostname or IP address for sending emails." />
            </label>
            <Input
              value={config.smtpHost || config.smtp_host || ""}
              onChange={(e) =>
                setEmailConfig(formData, setFormData, {
                  smtpHost: e.target.value,
                  smtp_host: e.target.value,
                })
              }
              placeholder="smtp.example.com"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">
              SMTP Port{" "}
              <HelpTooltip text="The port number for the SMTP server (typically 587 for TLS or 465 for SSL)." />
            </label>
            <Input
              type="number"
              value={config.smtpPort || config.smtp_port || 587}
              onChange={(e) =>
                setEmailConfig(formData, setFormData, {
                  smtpPort: Number(e.target.value),
                  smtp_port: Number(e.target.value),
                })
              }
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">
              SMTP Auth Method{" "}
              <HelpTooltip text="Use password auth, API key auth, or no auth for trusted relays." />
            </label>
            <Select
              value={authType}
              onChange={(e) =>
                setEmailConfig(formData, setFormData, {
                  smtpAuthType: e.target.value,
                  smtp_auth_type: e.target.value,
                })
              }
            >
              <option value="password">Username + Password</option>
              <option value="api_key">API Key</option>
              <option value="none">No Authentication</option>
            </Select>
          </div>

          {authType !== "none" && (
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                SMTP Username{" "}
                <HelpTooltip text="Username for SMTP auth. For many API-key SMTP providers, use 'apikey'." />
              </label>
              <Input
                value={config.smtpUsername || config.smtp_username || ""}
                onChange={(e) =>
                  setEmailConfig(formData, setFormData, {
                    smtpUsername: e.target.value,
                    smtp_username: e.target.value,
                  })
                }
                placeholder={authType === "api_key" ? "apikey" : "username"}
                required={authType === "password"}
              />
            </div>
          )}

          {authType === "password" && (
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                SMTP Password{" "}
                <HelpTooltip text="Password for SMTP authentication." />
              </label>
              <Input
                type="password"
                value={config.smtpPassword || config.smtp_password || ""}
                onChange={(e) =>
                  setEmailConfig(formData, setFormData, {
                    smtpPassword: e.target.value,
                    smtp_password: e.target.value,
                  })
                }
                placeholder="••••••••"
                required
              />
            </div>
          )}

          {authType === "api_key" && (
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                SMTP API Key{" "}
                <HelpTooltip text="API key used as SMTP auth secret (for example, SendGrid SMTP relay)." />
              </label>
              <Input
                type="password"
                value={config.smtpApiKey || config.smtp_api_key || ""}
                onChange={(e) =>
                  setEmailConfig(formData, setFormData, {
                    smtpApiKey: e.target.value,
                    smtp_api_key: e.target.value,
                  })
                }
                placeholder="••••••••"
                required
              />
            </div>
          )}

          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={
                  !!(
                    config.smtpStartTLS ||
                    config.smtp_starttls ||
                    config.starttls
                  )
                }
                onChange={(e) =>
                  setEmailConfig(formData, setFormData, {
                    smtpStartTLS: e.target.checked,
                    smtp_starttls: e.target.checked,
                    starttls: e.target.checked,
                  })
                }
                className="w-4 h-4"
              />
              <span className="text-sm text-sre-text">Use STARTTLS</span>
            </label>

            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={!!(config.smtpUseSSL || config.smtp_use_ssl)}
                onChange={(e) =>
                  setEmailConfig(formData, setFormData, {
                    smtpUseSSL: e.target.checked,
                    smtp_use_ssl: e.target.checked,
                  })
                }
                className="w-4 h-4"
              />
              <span className="text-sm text-sre-text">Use SSL/TLS</span>
            </label>
          </div>
        </>
      )}

      {provider === "sendgrid" && (
        <div>
          <label className="block text-sm font-medium text-sre-text mb-2">
            SendGrid API Key{" "}
            <HelpTooltip text="API key used for SendGrid Web API v3 email delivery." />
          </label>
          <Input
            type="password"
            value={
              config.sendgridApiKey ||
              config.sendgrid_api_key ||
              config.apiKey ||
              config.api_key ||
              ""
            }
            onChange={(e) =>
              setEmailConfig(formData, setFormData, {
                sendgridApiKey: e.target.value,
                sendgrid_api_key: e.target.value,
                apiKey: e.target.value,
                api_key: e.target.value,
              })
            }
            placeholder="SG.xxxxx"
            required
          />
        </div>
      )}

      {provider === "resend" && (
        <div>
          <label className="block text-sm font-medium text-sre-text mb-2">
            Resend API Key{" "}
            <HelpTooltip text="API key used for Resend email API delivery." />
          </label>
          <Input
            type="password"
            value={
              config.resendApiKey ||
              config.resend_api_key ||
              config.apiKey ||
              config.api_key ||
              ""
            }
            onChange={(e) =>
              setEmailConfig(formData, setFormData, {
                resendApiKey: e.target.value,
                resend_api_key: e.target.value,
                apiKey: e.target.value,
                api_key: e.target.value,
              })
            }
            placeholder="re_xxxxx"
            required
          />
        </div>
      )}
    </>
  );
}

EmailChannelFields.propTypes = {
  formData: PropTypes.shape({
    config: PropTypes.object,
  }).isRequired,
  setFormData: PropTypes.func.isRequired,
};
