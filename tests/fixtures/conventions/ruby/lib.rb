require 'json'
require 'nokogiri'

def used
  JSON.generate({})
end

def orphan
  Nokogiri::HTML('')
end
