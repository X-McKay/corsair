module Archive
  # List the entries of a tar archive.
  def self.list_entries(path)
    `tar -tf #{path}`.lines.map(&:chomp)
  end
end
