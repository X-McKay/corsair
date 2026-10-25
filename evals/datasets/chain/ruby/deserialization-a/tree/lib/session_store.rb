require 'base64'
require 'json'

module SessionStore
  # Restore a session from its cookie value.
  def self.restore(cookie)
    JSON.parse(Base64.strict_decode64(cookie))
  end
end
