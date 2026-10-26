require 'base64'

module SessionStore
  # Restore a session from its cookie value.
  def self.restore(cookie)
    Marshal.load(Base64.strict_decode64(cookie))
  end
end
