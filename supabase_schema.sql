-- Run this SQL in your Supabase SQL Editor to create the ball_by_ball table.

create table if not exists ball_by_ball (
  id              bigserial primary key,
  match_id        integer       not null,
  event_name      text,
  inning_number   integer,
  batting_team    text,
  bowling_team    text,
  over            integer,
  delivery        text,
  batter          text,
  bowler          text,
  total_runs      integer       default 0,
  batter_runs     integer       default 0,
  extras_runs     integer       default 0,
  extras_type     text,
  wickets         integer       default 0,
  bowler_wicket   integer       default 0,
  player_out      text,
  wicket_type     text,
  legal_delivery  integer       default 0,
  dots            integer       default 0,  -- was "0s"
  ones            integer       default 0,  -- was "1s"
  twos            integer       default 0,  -- was "2s"
  threes          integer       default 0,  -- was "3s"
  fours           integer       default 0,  -- was "4s"
  sixes           integer       default 0,  -- was "6s"
  wides           integer       default 0,
  scraped_at      timestamptz   default now()
);

-- Unique constraint used by the upsert (on_conflict)
create unique index if not exists ball_by_ball_unique_ball
  on ball_by_ball (match_id, inning_number, over, delivery, batter);

-- Useful indexes for query performance
create index if not exists idx_bbb_match_id    on ball_by_ball (match_id);
create index if not exists idx_bbb_event       on ball_by_ball (event_name);
create index if not exists idx_bbb_batter      on ball_by_ball (batter);
create index if not exists idx_bbb_bowler      on ball_by_ball (bowler);

-- Series metadata table for series_info_scraper.py
create table if not exists series_info (
  id               bigserial primary key,
  series_id        integer       not null unique,
  club_id          integer,
  series_name      text,
  season           text,
  status           text,
  series_format    text,
  venue            text,
  organizer        text,
  start_date       date,
  end_date         date,
  match_count      integer,
  teams            text[],
  team_count       integer,
  last_updated_by  text,
  last_updated_at  text,
  scraped_at       timestamptz   default now()
);

create unique index if not exists series_info_unique_series
  on series_info (series_id);

-- Player profile table for player_info_scraper.py
create table if not exists tca_db_player_info (
  id               bigserial primary key,
  player_id        integer       not null unique,
  club_id          integer,
  name             text,
  verified         boolean       default false,
  current_team     text,
  current_team_id  integer,
  teams            text[],
  age              integer,
  playing_role     text,
  batting_style    text,
  bowling_style    text,
  scraped_at       timestamptz   default now()
);

create unique index if not exists tca_db_player_info_unique_player
  on tca_db_player_info (player_id);

