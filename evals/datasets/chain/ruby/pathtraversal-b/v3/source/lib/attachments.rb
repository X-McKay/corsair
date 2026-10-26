module Attachments
  # Read a stored attachment by name under the given root.
  def self.read(root:, name:)
    File.read(File.join(root, name))
  end
end
