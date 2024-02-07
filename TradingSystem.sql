/*
 Navicat Premium Data Transfer

 Source Server         : jp
 Source Server Type    : MariaDB
 Source Server Version : 100521 (10.5.21-MariaDB-0+deb11u1)
 Source Host           : jparm.hubber.top:3306
 Source Schema         : TradingSystem

 Target Server Type    : MariaDB
 Target Server Version : 100521 (10.5.21-MariaDB-0+deb11u1)
 File Encoding         : 65001

 Date: 07/02/2024 21:04:02
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for TradingStatistics
-- ----------------------------
DROP TABLE IF EXISTS `TradingStatistics`;
CREATE TABLE `TradingStatistics` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `datetime` datetime DEFAULT NULL,
  `money` float DEFAULT NULL,
  `exId` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=30597 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table structure for exchange_info
-- ----------------------------
DROP TABLE IF EXISTS `exchange_info`;
CREATE TABLE `exchange_info` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `ex` varchar(255) NOT NULL COMMENT '交易所',
  `account` varchar(255) NOT NULL COMMENT '账号',
  `apikey` varchar(255) NOT NULL COMMENT 'apikey',
  `api_secret` varchar(255) NOT NULL COMMENT 'api_secret',
  `api_password` varchar(255) DEFAULT '' COMMENT 'api_password',
  `deleted` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table structure for order_info
-- ----------------------------
DROP TABLE IF EXISTS `order_info`;
CREATE TABLE `order_info` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `symbol` varchar(255) NOT NULL COMMENT '交易对名',
  `ex` int(11) NOT NULL COMMENT '交易所Id',
  `orderId` varchar(255) NOT NULL COMMENT '订单id',
  `posSide` varchar(255) NOT NULL COMMENT '方向',
  `size` float DEFAULT NULL COMMENT '头寸大小',
  `size_exec` float DEFAULT NULL COMMENT '已成交的头寸',
  `priceAvg` float DEFAULT NULL COMMENT '均价',
  `tp` float DEFAULT NULL COMMENT '止盈位',
  `tp_id` varchar(255) DEFAULT NULL COMMENT '止盈Id',
  `sl` float DEFAULT NULL COMMENT '止损位',
  `sl_id` varchar(255) DEFAULT NULL COMMENT '止损Id',
  `leverage` int(11) DEFAULT NULL COMMENT '杠杆',
  `isswap` tinyint(1) NOT NULL COMMENT '是否是合约',
  `marginMode` varchar(255) DEFAULT NULL COMMENT '保证金模式',
  `openTime` datetime DEFAULT NULL COMMENT '下单时间',
  `subPosId` varchar(255) DEFAULT NULL COMMENT '带单id',
  `delete` tinyint(1) DEFAULT NULL COMMENT '删除',
  `status` int(11) DEFAULT NULL COMMENT '状态',
  `orderFrom` varchar(255) DEFAULT NULL COMMENT '订单来源，web,tv',
  `orderType` int(13) DEFAULT NULL COMMENT '订单类型，0市价，1限价',
  `sltp_status` int(13) DEFAULT NULL COMMENT '订单止盈止损状态0未设1未生效2已经生效',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=87 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table structure for sltp_market
-- ----------------------------
DROP TABLE IF EXISTS `sltp_market`;
CREATE TABLE `sltp_market` (
  `id` int(13) NOT NULL AUTO_INCREMENT,
  `sl_id` int(13) DEFAULT NULL,
  `sl` float DEFAULT NULL,
  `tp_id` int(13) DEFAULT NULL,
  `tp` float DEFAULT NULL,
  `symbol` varchar(255) NOT NULL,
  `exId` int(13) NOT NULL,
  `isdelete` tinyint(1) DEFAULT NULL,
  `isswap` tinyint(1) DEFAULT NULL,
  `posSide` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_general_ci;

-- ----------------------------
-- Table structure for strategy_order
-- ----------------------------
DROP TABLE IF EXISTS `strategy_order`;
CREATE TABLE `strategy_order` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `symbol` varchar(255) NOT NULL,
  `condition1` float NOT NULL DEFAULT 0 COMMENT '条件1价格',
  `condition2` float NOT NULL DEFAULT 0 COMMENT '条件2价格',
  `condition1status` varchar(2) DEFAULT NULL COMMENT '条件1状态',
  `exids` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'exid列表' CHECK (json_valid(`exids`)),
  `opentime` datetime DEFAULT NULL COMMENT '开单时间',
  `deleted` tinyint(2) DEFAULT NULL COMMENT '是否已删除',
  `endtime` int(10) DEFAULT NULL COMMENT '结束时间秒',
  `posSide` varchar(255) DEFAULT NULL COMMENT '做单方向',
  `money` float DEFAULT NULL COMMENT '开单价格',
  `isswap` varchar(2) DEFAULT NULL COMMENT '是否是合约',
  `sl` float DEFAULT NULL,
  `tp` float DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_general_ci;

-- ----------------------------
-- Table structure for user
-- ----------------------------
DROP TABLE IF EXISTS `user`;
CREATE TABLE `user` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `account` varchar(255) DEFAULT NULL,
  `password` varchar(255) DEFAULT NULL,
  `privilege` tinyint(2) DEFAULT 0,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

SET FOREIGN_KEY_CHECKS = 1;
