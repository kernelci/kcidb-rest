#!/bin/bash
# SPDX-License-Identifier: LGPL-2.1-only
# Copyright (C) 2025 Collabora Ltd
# Author: Denys Fedoryshchenko <denys.f@collabora.com>
#
# This library is free software; you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by the Free
# Software Foundation; version 2.1.
#
# This library is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. See the GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with this library; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

# sudo and setup user/pass to postgres:postgres
sudo -u postgres createuser -s kcidb
sudo -u postgres dropdb kcidb
sudo -u postgres createdb -O kcidb kcidb
# set password for user kcidb
sudo -u postgres psql -c "ALTER USER kcidb WITH PASSWORD 'kcidb';"
# clean up old db kcidb
