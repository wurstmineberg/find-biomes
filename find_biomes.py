#!/usr/bin/env python3

"""Find coordinates with a given biome in a Minecraft world.

Usage:
  find-biomes [options] [<biome>...]
  find-biomes -h | --help

Options:
  -h, --help            Print this message and exit.
  -v, --verbose         Produce more detailed output.
  --api-url=<api_url>   Request all world data from this Wurstmineberg Minecraft API instance. [Default: https://api.wurstmineberg.de]
  --start-coords=<x,z>  Start at these coordinates instead of the world spawn.
  --world=<world_name>  Request world data for this world. Defaults to the main world.
"""

import collections
import docopt
import enum
import more_itertools
import requests

CACHE = {
    'all_chunks': None,
    'chunks': {},
    'world': None
}

biomes_response = requests.get('https://assets.wurstmineberg.de/json/biomes.json')
biomes_response.raise_for_status()
Biome = enum.Enum('Biomes', {
    biome_info['id']: int(int_id)
    for int_id, biome_info in biomes_response.json()['biomes'].items()
}, module=__name__)

def all_chunks_sorted_by_distance(arguments, start_x, start_z):
    if CACHE['all_chunks'] is None:
        if arguments['--verbose']:
            print('[....] downloading chunks overview', end='\r', flush=True)
        CACHE['all_chunks'] = api_json(arguments, '/v2/world/{world}/chunks/overview.json')
        if arguments['--verbose']:
            print('[ ok ]')
    start_chunk_x = start_x // 16
    start_chunk_z = start_z // 16
    result = collections.defaultdict(list)
    for chunk in CACHE['all_chunks']['overworld']:
        result[abs(chunk['x'] - start_chunk_x) + abs(chunk['z'] - start_chunk_z)].append(chunk)
    for chunk_distance, chunks in sorted(result.items()):
        for chunk in chunks:
            yield chunk_distance, chunk

def api_json(arguments, path):
    response = requests.get(arguments['--api-url'] + path.format(world=get_world(arguments)))
    response.raise_for_status()
    return response.json()

def get_closest_coords(arguments, biome, start_x, start_z):
    chunks_by_distance = list(all_chunks_sorted_by_distance(arguments, start_x, start_z))
    found_chunk_distance = None
    for i, (chunk_distance, chunk) in enumerate(chunks_by_distance):
        if arguments['--verbose']:
            progress = min(4, int(5 * i / len(chunks_by_distance)))
            print('[{}{}] searching for {}: {} out of {} chunks checked'.format('=' * progress, '.' * (4 - progress), biome.name, i, len(chunks_by_distance)), end='\r', flush=True)
        if found_chunk_distance is not None and chunk_distance > found_chunk_distance + 3:
            break # if the chunk distance is 4 more than the last found, the block distance cannot be smaller
        if (chunk['x'], chunk['z']) not in CACHE['chunks']:
            CACHE['chunks'][chunk['x'], chunk['z']] = api_json(arguments, '/v2/world/{{world}}/chunks/overworld/chunk/{}/0/{}.json'.format(chunk['x'], chunk['z']))[0]
        for row in CACHE['chunks'][chunk['x'], chunk['z']]:
            for block in row:
                if block['biome'] == biome.name:
                    if found_chunk_distance is None or abs(block['x'] - start_x) + abs(block['z'] - start_z) < abs(found_x - start_x) + abs(found_z - start_z):
                        found_chunk_distance = chunk_distance
                        found_x = block['x']
                        found_z = block['z']
    if arguments['--verbose']:
        print('[ ok ]')
    if found_chunk_distance is not None:
        return found_x, found_z

def get_world(arguments):
    if arguments['--world']:
        return arguments['--world']
    if CACHE['world'] is None:
        response = requests.get(arguments['--api-url'] + '/v2/server/worlds.json')
        response.raise_for_status()
        CACHE['world'] = more_itertools.one(world_name for world_name, world_info in response.json().items() if world_info['main'])
    return CACHE['world']

if __name__ == '__main__':
    arguments = docopt.docopt(__doc__)
    if arguments['<biome>']:
        biomes = [Biome[biome_str] for biome_str in arguments['<biome>']]
    else:
        biomes = list(Biome)
    if arguments['--start-coords']:
        start_x, start_z = (int(coord_str) for coord_str in arguments['--start-coords'].split(','))
    else:
        if arguments['--verbose']:
            print('[....] downloading level.json', end='\r', flush=True)
        level = api_json(arguments, '/v2/world/{world}/level.json')
        if arguments['--verbose']:
            print('[ ok ]')
        start_x = level['Data']['SpawnX']
        start_z = level['Data']['SpawnZ']
        if arguments['--verbose']:
            print('[ ** ] start coords: {},{}'.format(start_x, start_z))
    for biome in biomes:
        result = get_closest_coords(arguments, biome, start_x, start_z)
        if result is None:
            print('[ !! ] {}: not found'.format(biome.name))
        else:
            x, z = result
            print('[ ** ] {}: {},{} ({} blocks from {},{})'.format(biome.name, x, z, abs(x - start_x) + abs(z - start_z), start_x, start_z))
