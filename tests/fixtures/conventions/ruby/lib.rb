require 'json'
require 'nokogiri'

def used
  JSON.generate({})
end

def caller_fn
  used
end

def orphan
  Nokogiri::HTML('')
end
