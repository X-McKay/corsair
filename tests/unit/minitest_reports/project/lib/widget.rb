module Widget
  def self.escape(value)
    value.gsub("<", "&lt;")
  end
end
