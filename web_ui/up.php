<?php

require 'common.php';
require 'config.php';

use DigitalOceanV2\Adapter\BuzzAdapter;
use DigitalOceanV2\DigitalOceanV2;

$adapter = new BuzzAdapter($do_config['key']);
$digitalocean = new DigitalOceanV2($adapter);
$image = $digitalocean->image();
$images = array_filter($image->getAll(['private' => true]), function($im) {
    return strpos($im->name, $do_config['hostname']) === 0;
});
$latest_image = null;
foreach ($images as $im) {
    if ($latest_image === null or $im->name > $latest_image->name) {
        $latest_image = $im;
    }
}

var_dump($latest_image);

?>
