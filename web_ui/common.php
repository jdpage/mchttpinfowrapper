<?php

require 'vendor/autoload.php';

class RestObject {
    private $basename = null;
    private $anchor = null;
    private $result_body = null;

    function __construct($basename, $anchor) {
        $this->basename = $basename;
        $this->anchor = $anchor;
    }

    private function http_request($method, $url) {
        $options = array(
            'http' => array(
                'method' => $method,
                'timeout' => 10,
            ),
        );
        $context = stream_context_create($options);
        return file_get_contents($url, false, $context);
    }

    private function request_anchor($anchor) {
        return $this->http_request(
            $anchor->method,
            $this->basename . $anchor->href);
    }

    public function result() {
        if ($this->result_body === null) {
            $this->refresh();
        }
        return $this->result_body;
    }

    public function refresh() {
        $data = @$this->request_anchor($this->anchor);
        if ($data === false) {
            return false;
        }
        $this->result_body = json_decode($data);
        return true;
    }
}

class McHttpInfoEndpoint extends RestObject {
    function __construct($endpoint) {
        parent::__construct($endpoint, (object)array(
            'method' => 'GET',
            'href' => '/',
        ));
    }

    public function is_up() {
        return $this->refresh();
    }

    public function server_info() {
        return new McServerInfo(
            $this->basename,
            $this->result()->{'server info'});
    }

    public function player_info() {
        return new McPlayerInfo(
            $this->basename,
            $this->result()->{'player info'});
    }
}

?>
