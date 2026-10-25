# Reduced from secure_headers (github/secure_headers)
# lib/secure_headers/headers/content_security_policy.rb: ContentSecurityPolicy builds a
# single Content-Security-Policy directive string from a directive name and its source
# list. The source-list minifier is replaced by a plain join so the module runs offline.
module SecureHeaders
  class ContentSecurityPolicy
    def build_source_list_directive(directive, source_list)
      minified_source_list = source_list.join(" ")
      escaped_source_list = minified_source_list.gsub(/[\n;]/, " ")
      [directive, escaped_source_list].join(" ").strip
    end
  end
end
