require 'open3'

module Archive
  # List the entries of a tar archive.
  def self.list_entries(path)
    out, _status = Open3.capture2('tar', '-tf', path)
    out.lines.map(&:chomp)
  end
end
