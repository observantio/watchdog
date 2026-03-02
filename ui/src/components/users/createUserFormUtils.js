export const USERNAME_REGEX = /^[a-z0-9._-]{3,50}$/;
export const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function generateStrongPassword(length = 16) {
  const charset =
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*";
  let password = "";
  for (let i = 0; i < length; i += 1) {
    password += charset.charAt(Math.floor(Math.random() * charset.length));
  }
  return password;
}

export function validateCreateUserForm(
  formData,
  { requirePassword = true } = {},
) {
  const email = (formData.email || "").trim();
  const password = formData.password || "";
  const username = (formData.username || "").trim().toLowerCase();

  const errors = {};
  if (!username) errors.username = "Please enter a username";
  else if (!USERNAME_REGEX.test(username)) {
    errors.username =
      "Username must be 3-50 chars and use a-z, 0-9, ., _ or - (no spaces)";
  }

  if (!EMAIL_REGEX.test(email))
    errors.email = "Please enter a valid email address";

  if (requirePassword && password.length < 8) {
    errors.password = "Password must be at least 8 characters";
  }

  if (!requirePassword && password && password.length < 8) {
    errors.password = "If provided, password must be at least 8 characters";
  }

  return {
    normalized: {
      ...formData,
      username,
      email,
    },
    errors,
  };
}

export function buildCreateUserPayload(
  formData,
  { includePassword = true } = {},
) {
  const payload = {
    ...formData,
    username: (formData.username || "").trim().toLowerCase(),
    email: (formData.email || "").trim(),
  };

  if (!includePassword || !payload.password) {
    delete payload.password;
  }

  return payload;
}
