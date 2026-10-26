module HostCheck
  ALLOWED = /^[a-z0-9-]+\.example\.com$/

  # Whether a callback host belongs to the example.com estate.
  def self.allowed?(host)
    ALLOWED.match?(host)
  end
end
