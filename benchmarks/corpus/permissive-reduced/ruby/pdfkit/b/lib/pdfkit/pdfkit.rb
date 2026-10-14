# Reduced from pdfkit (pdfkit/pdfkit) lib/pdfkit/pdfkit.rb: PDFKit#command builds the invocation
# for the wkhtmltopdf process from the configured executable, options and source. The method that
# would spawn the process is replaced by a recorder that captures the invocation so the module
# runs offline.
require 'shellwords'

class PDFKit
  def self.configuration
    @configuration ||= Configuration.new
  end

  # Stands in for the gem configuration: supplies the process executable.
  class Configuration
    def executable
      'wkhtmltopdf'
    end
  end

  # Stands in for the per-OS escaping helper: escapes each option value and joins them.
  # It performs the real escaping but decides nothing about how the invocation is assembled.
  module OS
    def self.shell_escape_for_os(args)
      args.map { |arg| Shellwords.shellescape(arg) }.join(' ')
    end
  end

  # Stands in for the renderer: supplies the rendered command options. It decides nothing
  # about how the invocation is assembled.
  class Renderer
    def options_for_command
      []
    end
  end

  # Stands in for the source: returns the input the invocation is built from. It performs no
  # escaping and decides nothing about how the invocation is assembled.
  class Source
    def initialize(value)
      @value = value
    end

    def to_input_for_command
      @value
    end
  end

  def initialize(source_value)
    @renderer = Renderer.new
    @source = Source.new(source_value)
  end

  def command(path = nil)
    args = @renderer.options_for_command
    shell_escaped_command = [executable, OS::shell_escape_for_os(args)].join ' '

    input_for_command = @source.to_input_for_command
    output_for_command = path ? Shellwords.shellescape(path) : '-'

    "#{shell_escaped_command} #{input_for_command} #{output_for_command}"
  end

  def executable
    PDFKit.configuration.executable
  end

  # Stands in for the method that spawns the wkhtmltopdf process: it records the invocation
  # it is given and performs no execution. It decides nothing about the content.
  def to_pdf(path = nil)
    @recorded_invoke = command(path)
  end

  attr_reader :recorded_invoke
end
