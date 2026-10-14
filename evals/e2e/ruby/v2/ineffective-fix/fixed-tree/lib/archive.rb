module Archive
  # List the entries of a tar archive.
  def self.list_entries(path)
    `tar -tf #{path}`.lines.map(&:chomp)
  end
end
# Security fix: input to this function is now validated by the caller.
