<?php

include_once('common.php');

$hostname = 'http://104.236.113.74';

$root = new McHttpInfoEndpoint($hostname);
echo 'is up?';
$up = $root->is_up();
var_dump($up);

# $root = json_decode(http_request('GET', $hostname));
# $server_info = json_decode(
#     mc_request_anchor($root->{'server info'}, $hostname));
# $player_info = json_decode(
#     mc_request_anchor($root->{'player info'}, $hostname));
# $player_count = count(get_object_vars($player_info->players));
# 
# date_default_timezone_set('UTC');
# $server_uptime = strtotime($server_info->stats->uptime);
# var_dump($server_uptime);
# 
# if ($player_count > 0) {
#     echo json_encode(array(
#         "status" => "up",
#         "players" => $player_count,
#     ));
# } else {
# }

# try {
#     $r->send();
#     if ($r->getResponseCode() == 200) {
#         echo json_decode($r->getResponseBody());
#     }
# } catch (HttpException $ex) {
#     echo $ex;
# }
?>
