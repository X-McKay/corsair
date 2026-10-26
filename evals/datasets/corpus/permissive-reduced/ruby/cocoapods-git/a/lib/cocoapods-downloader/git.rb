# Reduced from cocoapods-downloader (CocoaPods/cocoapods-downloader) lib/cocoapods-downloader/git.rb:
# Pod::Downloader::Git.preprocess_options builds the argument list for the git ls-remote subcommand
# from the download options. The method that would spawn the git process is replaced by a recorder
# that captures the argument list so the module runs offline.
module Pod
  module Downloader
    class DownloaderError < StandardError; end

    class Git
      def self.preprocess_options(options)
        return options unless options[:branch]

        command = ['ls-remote',
                   options[:git],
                   options[:branch]]
        output = Git.execute_command('git', command)
        match = commit_from_ls_remote output, options[:branch]

        return options if match.nil?

        options[:commit] = match
        options.delete(:branch)

        options
      end

      def self.commit_from_ls_remote(output, branch_name)
        return nil if branch_name.nil?
        encoded_branch_name = branch_name.dup.force_encoding(Encoding::ASCII_8BIT)
        match = %r{([a-z0-9]*)\trefs\/(heads|tags)\/#{Regexp.quote(encoded_branch_name)}}.match(output)
        match[1] unless match.nil?
      end

      private_class_method :commit_from_ls_remote

      # Stands in for the inherited method that spawns the git process: it records the
      # argument list it is given and performs no execution. It decides nothing about the content.
      def self.execute_command(bin, command)
        @recorded_argv = [bin] + command
        ''
      end

      class << self
        attr_reader :recorded_argv
      end
    end
  end
end
