module HostCheck
  ALLOWED = /\A[a-z0-9-]+\.example\.com\z/

  # Whether a callback host belongs to the example.com estate.
  def self.allowed?(host)
    ALLOWED.match?(host)
  end
end
