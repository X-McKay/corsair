module Attachments
  ROOT = File.expand_path('../storage', __dir__)

  # Read a stored attachment by name.
  def self.read(name)
    File.read(File.join(ROOT, name))
  end
end
